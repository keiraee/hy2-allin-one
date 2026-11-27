#!/usr/bin/env python3
"""Subscription generation (HY2/VLESS direct links, Base64, Clash YAML, sing-box JSON)."""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

for _cand in (
    str(Path(__file__).resolve().parent) if "__file__" in globals() else "",
    "/usr/local/lib/hy2-aio",
    str(Path.cwd() / "app"),
):
    if _cand and _cand not in sys.path and (Path(_cand) / "common.py").is_file():
        sys.path.insert(0, _cand)

from common import (
    client_insecure,
    country_code_to_flag,
    obfs_enabled,
    port_hop_interval,
    port_hop_ports,
    reality_server_name,
    subscription_sni,
    xray_port,
)


def _http_get_json(url: str) -> Optional[dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


_GEO_CACHE: dict[str, tuple[str, float]] = {}
# 查不到只记一个窗口：一次网络抖动若被永久缓存，国旗会一直不出现，得重启后端才能恢复。
# ponytail: 固定 1 小时，够短到自愈、够长到不会每次请求都去挨 3×5s 超时；要更细就上退避。
GEO_FAILURE_RETRY = 3600.0


def server_country_code(env: dict[str, str]) -> str:
    # COUNTRY_CODE 显式覆盖（config.env）；否则按 PUBLIC_IP 查归属地，结果缓存
    override = str(env.get("COUNTRY_CODE") or "").strip().upper()
    if override:
        return override
    ip = str(env.get("PUBLIC_IP") or "")
    if not ip:
        return ""
    cached = _GEO_CACHE.get(ip)
    if cached is not None:
        code, stamp = cached
        if code or time.time() - stamp < GEO_FAILURE_RETRY:
            return code
    code = ""
    for url in (
        f"https://ipwho.is/{ip}",
        f"https://api.ip.sb/geoip/{ip}",
        f"https://freeipapi.com/api/json/{ip}",
    ):
        data = _http_get_json(url) or {}
        if data.get("success") is False:
            continue
        candidate = str(data.get("country_code") or data.get("countryCode") or "").strip().upper()
        if len(candidate) == 2 and candidate.isalpha():
            code = candidate
            break
    _GEO_CACHE[ip] = (code, time.time())
    return code


def flag_prefix(env: dict[str, str]) -> str:
    flag = country_code_to_flag(server_country_code(env))
    return flag + " " if flag else ""


def direct_link(env: dict[str, str], username: str, password: str) -> str:
    """单节点 HY2 直链。

    端口跳跃时不能把范围塞进 host:port —— "8443-9443" 不是合法 URI 端口，
    v2rayN / CMA 按 Uri 解析会直接失败，服务器和端口都变成空（真机上就看到
    「没端口没服务器」）。端口范围必须走 mport 查询参数。

    依据 v2rayN ServiceLib/Handler/Fmt/Hysteria2Fmt.cs：
        item.Port  = url.Port == -1 ? 443 : url.Port;      // 主端口单独给
        Ports       = GetQueryDecoded(query, "mport");      // 范围走这里
        dicQuery.Add("mport", Ports.Replace(':', '-'));     // 起始-结束
    """
    # userinfo 里的冒号必须是【分隔符】，不能一起编码。
    # quote(f"{u}:{p}", safe="") 会把 : 编成 %3A，客户端解析
    # "hysteria2://u%3Ap@host" 时 username 拿到 "u:p"、password 为空，
    # 认证必然失败（真机上 v2ray 节点就是这么连不上的，Clash 走 YAML
    # 直接给 password 字段所以不受影响）。
    # 正确做法：用户名和密码各自编码，冒号原样保留。
    auth = (
        urllib.parse.quote(str(username), safe="")
        + ":"
        + urllib.parse.quote(str(password), safe="")
    )
    query_items: dict[str, str] = {
        "sni": subscription_sni(env),
    }
    if obfs_enabled(env):
        query_items["obfs"] = "salamander"
        query_items["obfs-password"] = env["OBFS_PASSWORD"]
    if client_insecure(env):
        query_items["insecure"] = "1"
    # 端口跳跃：主端口用区间起点，范围额外写进 mport
    hop = port_hop_ports(env)
    if hop:
        query_items["mport"] = hop
        port = hop.split("-", 1)[0]
    else:
        port = env.get("HY2_PORT", "443")
    query = urllib.parse.urlencode(query_items)
    name = urllib.parse.quote(flag_prefix(env) + f"HY2-{username}", safe="")
    return f"hysteria2://{auth}@{env['PUBLIC_IP']}:{port}/?{query}#{name}"


def new_vless_id() -> str:
    return str(uuid.uuid4())


VLESS_NODE_NAME = "hy2超时备用临时节点"


def vless_link(env: dict[str, str], username: str, info: Optional[dict[str, Any]] = None) -> str:
    payload = info if isinstance(info, dict) else {}
    vless_id = str(payload.get("vless_id") or "").strip()
    public_key = str(env.get("REALITY_PUBLIC_KEY") or "").strip()
    short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
    if not (vless_id and public_key and short_id):
        return ""
    query = urllib.parse.urlencode(
        {
            "encryption": "none",
            "flow": "xtls-rprx-vision",
            "security": "reality",
            "sni": reality_server_name(env),
            "fp": "chrome",
            "pbk": public_key,
            "sid": short_id,
            "type": "tcp",
        }
    )
    name = urllib.parse.quote(flag_prefix(env) + VLESS_NODE_NAME, safe="")
    return f"vless://{vless_id}@{env['PUBLIC_IP']}:{xray_port(env)}?{query}#{name}"


def direct_links(env: dict[str, str], username: str, password: str, info: Optional[dict[str, Any]] = None) -> str:
    lines = [direct_link(env, username, password)]
    extra = vless_link(env, username, info)
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def subscription_base64(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
) -> bytes:
    """通用订阅：节点 URI 按行拼起来再整个 base64。

    这是 v2ray 系的公共约定（v2rayN / v2rayNG / Shadowrocket / NekoBox
    都认）：拿到响应先判断能不能 base64 解码，解出来按行解析每条链接。
    v2rayN 的 SubscriptionHandler.cs 就是这么做的。

    直接用已有的 direct_link/vless_link，保证三种格式的节点完全一致 ——
    分叉成两份实现迟早会出现「Clash 能连、v2ray 连不上」这种鬼问题。
    """
    text = direct_links(env, username, password, info)
    return base64.b64encode(text.encode("utf-8"))


def subscription_singbox(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
    *,
    mode: Optional[dict[str, Any]] = None,
) -> bytes:
    """sing-box 远程配置（Remote Profile）。

    官方文档 docs/clients/general.md 写明：Remote Profile 代表一份远程
    **sing-box 配置**，图形客户端用
      sing-box://import-remote-profile?url=...#name
    导入。所以这里给的是完整 JSON，不是 Clash YAML —— 给 YAML 会解析失败。

    ⚠️ 认证差异（官方 hysteria2 文档专门警告过）：
    服务端用 auth.type=userpass 时，密码实际是 <用户名>:<密码>；
    sing-box 不提供 userpass 这层别名，必须把组合整个填进 password。
    填错会一直认证失败且很难查，这里单独拎出来注释。
    """
    payload = info if isinstance(info, dict) else {}
    tag_hy2 = flag_prefix(env) + "HY2-" + username
    mode = mode if isinstance(mode, dict) else {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}

    outbounds: list[dict[str, Any]] = []

    hy2: dict[str, Any] = {
        "type": "hysteria2",
        "tag": tag_hy2,
        "server": env["PUBLIC_IP"],
        "password": f"{username}:{password}",   # userpass 组合，不是裸密码
        "tls": {
            "enabled": True,
            # SNI 用订阅证书域名(与 Clash/直链一致),不能用 REALITY 的伪装
            # 域名 —— Hysteria 的证书是 Let's Encrypt 签给 DOMAIN 的,SNI
            # 必须对上才能严格校验。之前这里硬编码 insecure=True 且 SNI 用
            # REALITY 伪装域名,既削弱安全(v2rayNG 26.2.6+ 直接拒绝连接:
            # "未加密连接,请启用 TLS 或固定证书")又与证书不匹配。
            "server_name": subscription_sni(env),
            "insecure": bool(client_insecure(env)),
        },
    }
    hop_ports = port_hop_ports(env)
    if hop_ports:
        # sing-box 1.11+ 用 server_ports（端口范围），跟 Clash 的 ports 语义一致
        hy2["server_ports"] = [hop_ports.replace("-", ":")]
        # sing-box 的 hop_interval 要带时间单位（"30s"），裸数字 "30" 会报
        # time: missing unit in duration。Clash 那边才是裸秒数。
        _hop = str(port_hop_interval(env) or "30").strip()
        hy2["hop_interval"] = _hop if _hop.endswith("s") else _hop + "s"
    else:
        hy2["server_port"] = int(env.get("HY2_PORT", "443") or 443)
    if obfs_enabled(env):
        hy2["obfs"] = {"type": "salamander", "password": env["OBFS_PASSWORD"]}
    if mode.get("mode") == "brutal":
        hy2["up_mbps"] = int(float(mode["up_mbps"]))
        hy2["down_mbps"] = int(float(mode["down_mbps"]))
    outbounds.append(hy2)

    vless_id = str(payload.get("vless_id") or "").strip()
    public_key = str(env.get("REALITY_PUBLIC_KEY") or "").strip()
    short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
    if vless_id and public_key and short_id:
        outbounds.append(
            {
                "type": "vless",
                "tag": flag_prefix(env) + VLESS_NODE_NAME,
                "server": env["PUBLIC_IP"],
                "server_port": int(xray_port(env)),
                "uuid": vless_id,
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": reality_server_name(env),
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                    "reality": {
                        "enabled": True,
                        "public_key": public_key,
                        "short_id": short_id,
                    },
                },
            }
        )

    tags = [item["tag"] for item in outbounds]
    outbounds.append({"type": "selector", "tag": "proxy", "outbounds": tags, "default": tags[0]})
    outbounds.append({"type": "direct", "tag": "direct"})

    config = {
        "log": {"level": "info"},
        # 规则集下载用的 HTTP 客户端。sing-box 1.14 的坑:
        #   - http_client 拨号 detour 到 direct 出站(不管 direct 有没有参数)
        #     一律报「detour to an empty direct outbound makes no sense」
        #     -> 服务起不来(真机踩过)
        #   - 不写 http_clients 则触发 implicit default HTTP client 弃用警告
        # 正解:顶层 http_clients 定义一个不带 detour 的客户端 --
        # 走系统默认路由直连,等价于旧 download_detour=direct 的语义,
        # 无警告无报错(真机 sing-box 1.14.4 run 验证 0 输出)。
        "http_clients": [
            {"tag": "dl-direct"}
        ],
        # DNS 用 sing-box 1.12+ 的新格式（type + server），旧写法
        # {"address": "https://1.1.1.1/dns-query"} 在 1.14.0 已彻底移除，
        # 导入会直接报「legacy DNS server formats are deprecated」。
        # 官方 migration 文档：https://sing-box.sagernet.org/migration/
        "dns": {
            # ⚠️ 境外域名必须「走代理」去查，否则会被污染。
            # 真机 2026-11-25：googlevideo.com（YouTube CDN）解析出一串
            # 根本不属于 Google 的 IP —— 31.13.94.37/31.13.95.169（Facebook 段）、
            # 199.59.149.230（Twitter）、59.24.3.173… 全是污染结果。
            # 即使路由规则正确把流量交给代理，代理也是去连这些假 IP，
            # 拿 SNI=googlevideo.com 去连 Facebook:443，必然失败 → YouTube 打不开。
            # detour 让 DoH 查询本身经代理发出，绕开本地污染。
            "servers": [
                {"type": "https", "tag": "remote", "server": "1.1.1.1", "detour": "proxy"},
                {"type": "https", "tag": "remote-alt", "server": "8.8.8.8", "detour": "proxy"},
                {"type": "local", "tag": "local"},
            ],
            # 只解析 IPv4(等价于 Clash 订阅的 ipv6: false)。
            # 2026-11-23 真机事故:WiFi 无 IPv6 时,sing-box 把国内域名
            # 解析成 AAAA(2408:... 联通 v6 段),判为国内直连 → direct
            # 经 wlan0 连 v6 → "network is unreachable",抖音搜索 /
            # 小红书头像全部转圈。蜂窝有 v6 所以流量正常;Clash 有
            # ipv6:false 所以正常 —— 只有 sing-box 在没有 v6 的 WiFi 上炸。
            "strategy": "ipv4_only",
            # 国内域名用本地 DNS（快，且国内域名不会被污染）。
            # 其余一律走 remote（经代理的 DoH）—— 这是治污染的关键。
            # 注意 dns.rules 的 server 字段在 1.12+ 仍可用（废弃的是 outbound）。
            "rules": [
                {"domain_suffix": [".cn"], "server": "local"},
                {"rule_set": "geosite-cn", "server": "local"},
            ],
            "final": "remote",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                # 只给 tun 分配 IPv4。带 IPv6 地址会让系统误以为有 v6,
                # 应用把 v6 包送进 tun、再被 direct 送回 wlan0 → unreachable
                # (同 2026-11-23 事故)。
                "address": ["172.19.0.1/30"],
                "auto_route": True,
                "strict_route": True,
                # MTU 显式收窄:WiFi 默认 1500,代理封装后撞上 PPPoE(1492)
                # 之类小 MTU 链路会分片丢包 → 大图 / 长页面加载卡。1400 为安全值。
                "mtu": 1400,
            }
        ],
        "outbounds": outbounds,
        "route": {
            # 国内分流:与 Clash 订阅的 china-domain + china-ip 对齐。
            # 之前只有 ip_is_private 直连、final=proxy,微信图片上传等
            # 国内大流量通道被 tun 全量代理绕道日本 → iOS 上发图必失败
            # (sing-box 官方 issue #2492,Android 用 rule-set 分流即解决)。
            "rule_set": [
                {
                    "tag": "geosite-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs",
                    "http_client": "dl-direct",
                    "update_interval": "48h",
                },
                {
                    "tag": "geoip-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs",
                    "http_client": "dl-direct",
                    "update_interval": "48h",
                },
                {
                    # 明确「非要走代理」的海外域名。用途是挡住 geoip 误判：
                    # googlevideo.com 这类海外域名会解析到国内 CDN IP，
                    # 只有 IP 规则会把它判成直连 → 5s i/o timeout。
                    "tag": "geosite-geolocation-!cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/geolocation-!cn.srs",
                    "http_client": "dl-direct",
                    "update_interval": "48h",
                },
            ],
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_is_private": True, "outbound": "direct"},
                # ⚠️ 顺序不能合并成 [geosite-cn, geoip-cn] 一条 —— 那是 OR 关系，
                # geoip 命中就直连，域名判断被完全绕过。真机 2026-11-25：
                # googlevideo.com(YouTube CDN) 解析到国内联通 IP →
                # 被 geoip-cn 判直连 → i/o timeout 5s。
                # 正确顺序：域名(国内→直连) → 域名(海外→代理) → IP(国内→直连)
                {"rule_set": ["geosite-cn"], "outbound": "direct"},
                {"rule_set": ["geosite-geolocation-!cn"], "outbound": "proxy"},
                {"rule_set": ["geoip-cn"], "outbound": "direct"},
            ],
            "final": "proxy",
            "auto_detect_interface": True,
            # 替代已废弃的 dns.rules[].outbound
            "default_domain_resolver": "local",
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")


def subscription_body(
    fmt: str,
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
    *,
    mode: Optional[dict[str, Any]] = None,
) -> tuple[bytes, str]:
    """按格式返回 (内容, Content-Type)。fmt 已归一化。"""
    if fmt == "singbox":
        return subscription_singbox(env, username, password, info, mode=mode), "application/json; charset=utf-8"
    if fmt == "v2ray":
        return subscription_base64(env, username, password, info), "text/plain; charset=utf-8"
    return subscription_yaml(env, username, password, info, mode=mode), "text/yaml; charset=utf-8"


def subscription_format_from_ua(user_agent: str) -> str:
    """按 User-Agent 猜客户端想要的格式。

    顺序很重要：sing-box 的 UA 里也可能带 "v2ray" 之类的字样，必须先判它。
    mihomo/clash 放前面是因为它们的 UA 很明确，且 Clash YAML 是默认格式。
    """
    ua = (user_agent or "").lower()
    if not ua:
        return "v2ray"          # 浏览器/curl：给通用 base64，兼容性最好
    if "sing-box" in ua or "singbox" in ua or ua.startswith("sfa/") or ua.startswith("sfi/") or ua.startswith("sfm/"):
        return "singbox"
    if "clash" in ua or "mihomo" in ua or "flclash" in ua or "stash" in ua:
        return "clash"
    if "v2ray" in ua or "shadowrocket" in ua or "nekobox" in ua or "nekoray" in ua:
        return "v2ray"
    return "v2ray"


def normalize_subscription_format(raw: str) -> str:
    """把用户传的 ?fmt= 归一化成三种之一；认不出返回空串（不走强制）。"""
    value = (raw or "").strip().lower().replace("-", "").replace("_", "")
    if value in ("clash", "mihomo", "yaml", "meta"):
        return "clash"
    if value in ("v2ray", "v2rayn", "v2rayng", "base64", "b64", "mixed", "link"):
        return "v2ray"
    if value in ("singbox", "sb", "sfa", "sfi", "sfm", "json"):
        return "singbox"
    return ""


def subscription_yaml(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
    *,
    mode: Optional[dict[str, Any]] = None,
) -> bytes:
    def q(value: str) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    mode = mode if isinstance(mode, dict) else {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    rate_lines = ""
    if mode.get("mode") == "brutal":
        rate_lines = (
            f'    up: "{float(mode["up_mbps"]):g} Mbps"\n'
            f'    down: "{float(mode["down_mbps"]):g} Mbps"\n'
        )

    obfs_lines = ""
    if obfs_enabled(env):
        obfs_lines = (
            "    obfs: salamander\n"
            f"    obfs-password: {q(env['OBFS_PASSWORD'])}\n"
        )

    hop_lines = ""
    hop_ports = port_hop_ports(env)
    if hop_ports:
        hop_lines = (
            f"    ports: {q(hop_ports)}\n"
            f"    hop-interval: {port_hop_interval(env)}\n"
        )

    node = q(flag_prefix(env) + "HY2-" + username)
    vless_block = ""
    vless_group = ""
    payload = info if isinstance(info, dict) else {}
    vless_id = str(payload.get("vless_id") or "").strip()
    public_key = str(env.get("REALITY_PUBLIC_KEY") or "").strip()
    short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
    if vless_id and public_key and short_id:
        vless_name = q(flag_prefix(env) + VLESS_NODE_NAME)
        vless_group = f"      - {vless_name}\n"
        vless_block = (
            f"  - name: {vless_name}\n"
            "    type: vless\n"
            f"    server: {q(env['PUBLIC_IP'])}\n"
            f"    port: {xray_port(env)}\n"
            f"    uuid: {q(vless_id)}\n"
            "    network: tcp\n"
            "    tls: true\n"
            "    udp: true\n"
            "    flow: xtls-rprx-vision\n"
            f"    servername: {q(reality_server_name(env))}\n"
            "    client-fingerprint: chrome\n"
            "    reality-opts:\n"
            f"      public-key: {q(public_key)}\n"
            f"      short-id: {q(short_id)}\n"
        )
    content = f"""mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
geodata-mode: true
geox-url:
  geosite: "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite-lite.dat"
ipv6: false

tun:
  enable: true
  stack: system
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  route-exclude-address:
    - {q(env["PUBLIC_IP"] + "/32")}
  dns-hijack:
    - any:53
    - tcp://any:53

dns:
  enable: true
  ipv6: false
  respect-rules: false
  default-nameserver:
    - 223.5.5.5
    - 119.29.29.29
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter-mode: whitelist
  fake-ip-filter:
    - "+.lan"
    - "+.local"
  nameserver:
    - https://1.1.1.1/dns-query#PROXY
    - https://8.8.8.8/dns-query#PROXY
  nameserver-policy:
    "geosite:cn":
      - https://doh.pub/dns-query
      - https://dns.alidns.com/dns-query
  proxy-server-nameserver:
    - 223.5.5.5
    - 119.29.29.29
  direct-nameserver:
    - system
  direct-nameserver-follow-policy: false

proxies:
  - name: {node}
    type: hysteria2
    server: {q(env["PUBLIC_IP"])}
    port: {env.get('HY2_PORT', '443')}
{rate_lines}    password: {q(username + ":" + password)}
{obfs_lines}{hop_lines}    sni: {q(subscription_sni(env))}
    skip-cert-verify: {"true" if client_insecure(env) else "false"}
    udp: true
    keepalive: 5s
{vless_block}
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - {node}
{vless_group}      - DIRECT

rule-providers:
  china-ip:
    type: http
    behavior: ipcidr
    format: mrs
    path: ./ruleset/china-ip.mrs
    interval: 86400
    url: https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geoip/cn.mrs

rules:
  - DOMAIN-SUFFIX,lan,DIRECT
  - DOMAIN-SUFFIX,jinritemai.com,DIRECT
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - GEOSITE,cn,DIRECT
  - GEOSITE,geolocation-!cn,PROXY
  - RULE-SET,china-ip,DIRECT
  - MATCH,PROXY
"""
    return content.encode("utf-8")
