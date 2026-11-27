#!/usr/bin/env python3
"""Subscription generation (HY2/VLESS direct links, Base64, Clash YAML, sing-box JSON)."""
from __future__ import annotations

import base64
import json
import re
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

# 单一分流意图层（Single IR）：Clash (.mrs) 与 sing-box (.srs) 均由此编译生成，
# 确保两端规则集同源、顺序一致、手写补丁零遗漏。
RULESET_MIRROR_BASES: tuple[str, ...] = (
    "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat",
    "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat",
    "https://gcore.jsdelivr.net/gh/MetaCubeX/meta-rules-dat",
    "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat",
)
RULESET_DEFAULT_MIRROR = RULESET_MIRROR_BASES[0]

ROUTING_RULESETS: tuple[dict[str, str], ...] = (
    {
        "tag": "geosite-private",
        "behavior": "domain",
        "mrs_file": "geosite-private.mrs",
        "srs_file": "geosite-private.srs",
        "mrs_upstream": "@meta/geo/geosite/private.mrs",
        "srs_upstream": "@sing/geo/geosite/private.srs",
    },
    {
        "tag": "geosite-cn",
        "behavior": "domain",
        "mrs_file": "geosite-cn.mrs",
        "srs_file": "geosite-cn.srs",
        "mrs_upstream": "@meta/geo/geosite/cn.mrs",
        "srs_upstream": "@sing/geo/geosite/cn.srs",
    },
    {
        "tag": "geosite-geolocation-!cn",
        "behavior": "domain",
        "mrs_file": "geosite-geolocation-!cn.mrs",
        "srs_file": "geosite-geolocation-!cn.srs",
        "mrs_upstream": "@meta/geo/geosite/geolocation-!cn.mrs",
        "srs_upstream": "@sing/geo/geosite/geolocation-!cn.srs",
    },
    {
        "tag": "geoip-cn",
        "behavior": "ipcidr",
        "mrs_file": "geoip-cn.mrs",
        "srs_file": "geoip-cn.srs",
        "mrs_upstream": "@meta/geo/geoip/cn.mrs",
        "srs_upstream": "@sing/geo/geoip/cn.srs",
    },
)

# 两端共享的手写补充直连域名后缀（仅做极少数缺口补丁）
CUSTOM_DIRECT_SUFFIXES: tuple[str, ...] = (
    "lan",
    "local",
    "jinritemai.com",
)


def _ruleset_upstream_url(upstream: str, base: str = RULESET_DEFAULT_MIRROR) -> str:
    if "raw.githubusercontent.com" in base and upstream.startswith("@"):
        return f"{base}/{upstream[1:]}"
    return f"{base}{upstream}"


def ruleset_url(env: dict[str, str], filename: str, upstream: str) -> str:
    """规则集下载地址（先统一走镜像，后续由同源托管层接管）。"""
    return _ruleset_upstream_url(upstream)


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


def parse_singbox_version(user_agent: str = "", sbver: str = "") -> tuple[int, int]:
    """提取客户端 sing-box 内核主次版本号；未识别时默认最新标准 (1, 14)。

    优先级：显式 ?sbver= 参数 > UA 中的 sing-box X.Y > 官方客户端前缀 SFA/SFI/SFM/SFT X.Y。
    这样第三方壳（如 Husi/0.5 (sing-box 1.12.8)）也能拿到真实内核版本而不是壳版本。
    """
    explicit = (sbver or "").strip()
    if explicit:
        m = re.search(r"v?(\d+)\.(\d+)", explicit, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
    ua = (user_agent or "").strip()
    if ua:
        m = re.search(r"sing-?box[/\s]+v?(\d+)\.(\d+)", ua, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(?:^|\s)(?:sfa|sfi|sfm|sft|sfl)/v?(\d+)\.(\d+)", ua, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
    return (1, 14)


def subscription_singbox(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
    *,
    mode: Optional[dict[str, Any]] = None,
    sb_version: Optional[tuple[int, int]] = None,
    user_agent: str = "",
    sbver: str = "",
) -> bytes:
    """sing-box 远程配置（Remote Profile），按客户端版本自适应兼容 1.11 / 1.12~1.13 / 1.14+。

    官方文档 docs/clients/general.md 写明：Remote Profile 代表一份远程
    **sing-box 配置**，图形客户端用
      sing-box://import-remote-profile?url=...#name
    导入。所以这里给的是完整 JSON，不是 Clash YAML —— 给 YAML 会解析失败。

    ⚠️ 认证差异（官方 hysteria2 文档专门警告过）：
    服务端用 auth.type=userpass 时，密码实际是 <用户名>:<密码>；
    sing-box 不提供 userpass 这层别名，必须把组合整个填进 password。
    填错会一直认证失败且很难查，这里单独拎出来注释。
    """
    ver = sb_version if sb_version is not None else parse_singbox_version(user_agent, sbver)
    is_114_plus = ver >= (1, 14)
    is_112_plus = ver >= (1, 12)

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
            "server_name": subscription_sni(env),
            "insecure": bool(client_insecure(env)),
        },
    }
    hop_ports = port_hop_ports(env)
    if hop_ports:
        hy2["server_ports"] = [hop_ports.replace("-", ":")]
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

    def _ruleset_item(tag: str, url: str) -> dict[str, Any]:
        item: dict[str, Any] = {
            "tag": tag,
            "type": "remote",
            "format": "binary",
            "url": url,
            "update_interval": "48h",
        }
        if is_114_plus:
            item["http_client"] = "dl-direct"
        else:
            item["download_detour"] = "direct"
        return item

    if is_112_plus:
        dns_servers: list[dict[str, Any]] = [
            {"type": "https", "tag": "remote", "server": "1.1.1.1", "detour": "proxy"},
            {"type": "https", "tag": "remote-alt", "server": "8.8.8.8", "detour": "proxy"},
            {"type": "local", "tag": "local"},
        ]
        dns_rules: list[dict[str, Any]] = [
            {"domain_suffix": [".cn", *CUSTOM_DIRECT_SUFFIXES], "server": "local"},
            {"rule_set": ["geosite-private", "geosite-cn"], "server": "local"},
        ]
    else:
        dns_servers = [
            {"tag": "remote", "address": "https://1.1.1.1/dns-query", "detour": "proxy"},
            {"tag": "remote-alt", "address": "https://8.8.8.8/dns-query", "detour": "proxy"},
            {"tag": "local", "address": "local"},
        ]
        dns_rules = [
            {"outbound": "any", "server": "local"},
            {"domain_suffix": [".cn", *CUSTOM_DIRECT_SUFFIXES], "server": "local"},
            {"rule_set": ["geosite-private", "geosite-cn"], "server": "local"},
        ]

    route_block: dict[str, Any] = {
        "rule_set": [
            _ruleset_item(
                rs["tag"],
                ruleset_url(env, rs["srs_file"], rs["srs_upstream"]),
            )
            for rs in ROUTING_RULESETS
        ],
        "rules": [
            {"action": "sniff"},
            {"protocol": "dns", "action": "hijack-dns"},
            {"ip_is_private": True, "outbound": "direct"},
            {"domain_suffix": list(CUSTOM_DIRECT_SUFFIXES), "outbound": "direct"},
            # 顺序：私有域名 → 国内域名直连 → 海外域名代理 → 国内纯 IP 兜底直连（禁止合并成 OR 单条）
            {"rule_set": ["geosite-private"], "outbound": "direct"},
            {"rule_set": ["geosite-cn"], "outbound": "direct"},
            {"rule_set": ["geosite-geolocation-!cn"], "outbound": "proxy"},
            {"rule_set": ["geoip-cn"], "outbound": "direct"},
        ],
        "final": "proxy",
        "auto_detect_interface": True,
    }
    if is_112_plus:
        route_block["default_domain_resolver"] = "local"

    cache_file: dict[str, Any] = {"enabled": True}
    if is_114_plus:
        cache_file["store_dns"] = True

    config: dict[str, Any] = {"log": {"level": "info"}}
    if is_114_plus:
        # sing-box 1.14+ 专用顶层 http_clients（低于 1.14 出现未知字段会直接启动失败）
        config["http_clients"] = [{"tag": "dl-direct"}]
    config.update(
        {
            "dns": {
                "servers": dns_servers,
                "strategy": "ipv4_only",
                "rules": dns_rules,
                "final": "remote",
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "address": ["172.19.0.1/30"],
                    "auto_route": True,
                    "strict_route": True,
                    "mtu": 1400,
                }
            ],
            "outbounds": outbounds,
            "route": route_block,
            "experimental": {"cache_file": cache_file},
        }
    )
    return json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")


def subscription_body(
    fmt: str,
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
    *,
    mode: Optional[dict[str, Any]] = None,
    user_agent: str = "",
    sbver: str = "",
) -> tuple[bytes, str]:
    """按格式返回 (内容, Content-Type)。fmt 已归一化。"""
    if fmt == "singbox":
        return (
            subscription_singbox(
                env, username, password, info, mode=mode, user_agent=user_agent, sbver=sbver
            ),
            "application/json; charset=utf-8",
        )
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
    if (
        "sing-box" in ua
        or "singbox" in ua
        or ua.startswith(("sfa/", "sfi/", "sfm/", "sft/", "sfl/"))
    ):
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
    provider_blocks = []
    for rs in ROUTING_RULESETS:
        url = ruleset_url(env, rs["mrs_file"], rs["mrs_upstream"])
        provider_blocks.append(
            f"  {rs['tag']}:\n"
            "    type: http\n"
            f"    behavior: {rs['behavior']}\n"
            "    format: mrs\n"
            f"    path: ./ruleset/{rs['mrs_file']}\n"
            "    interval: 86400\n"
            f"    url: {url}"
        )
    rule_providers_yaml = "\n".join(provider_blocks)
    custom_direct_rules = "\n".join(
        f"  - DOMAIN-SUFFIX,{suffix},DIRECT" for suffix in CUSTOM_DIRECT_SUFFIXES
    )

    content = f"""mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
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

sniffer:
  enable: true
  force-dns-mapping: true
  parse-pure-ip: true
  override-destination: true
  sniff:
    HTTP:
      ports: [80, 8080-8880]
      override-destination: true
    TLS:
      ports: [443, 8443]
    QUIC:
      ports: [443, 8443]
  skip-domain:
    - "Mijia Cloud"
    - "+.push.apple.com"

dns:
  enable: true
  ipv6: false
  respect-rules: false
  default-nameserver:
    - 223.5.5.5
    - 119.29.29.29
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter-mode: blacklist
  fake-ip-filter:
    - "+.lan"
    - "+.local"
    - "+.arpa"
    - "localhost.ptlogin2.qq.com"
    - "+.msftconnecttest.com"
    - "+.msftncsi.com"
    - "time.*.com"
    - "ntp.*.com"
    - "+.push.apple.com"
    - "rule-set:geosite-private"
    - "rule-set:geosite-cn"
  nameserver:
    - https://1.1.1.1/dns-query#PROXY
    - https://8.8.8.8/dns-query#PROXY
  nameserver-policy:
    "+.lan":
      - system
    "+.local":
      - system
    "rule-set:geosite-private":
      - system
    "rule-set:geosite-cn":
      - https://doh.pub/dns-query
      - https://dns.alidns.com/dns-query
  proxy-server-nameserver:
    - 223.5.5.5
    - 119.29.29.29
  direct-nameserver:
    - https://doh.pub/dns-query
    - https://dns.alidns.com/dns-query
  direct-nameserver-follow-policy: true

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
{rule_providers_yaml}

rules:
{custom_direct_rules}
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - RULE-SET,geosite-private,DIRECT
  - RULE-SET,geosite-cn,DIRECT
  - RULE-SET,geosite-geolocation-!cn,PROXY
  - RULE-SET,geoip-cn,DIRECT
  - MATCH,PROXY
"""
    return content.encode("utf-8")
