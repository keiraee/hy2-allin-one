"""多客户端订阅：Clash YAML / v2ray base64 / sing-box JSON。

三份内容必须描述同一批节点 —— 分叉成两套实现迟早会出现
「Clash 能连、v2ray 连不上」这种查半天的问题。
"""

import base64
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "app" / "server.py"


def load_ns():
    src = BACKEND.read_text(encoding="utf-8")
    ns = {"__name__": "hy2_sub_test"}
    exec(compile(src, "server.py", "exec"), ns)
    return ns


def make_env(**over):
    env = {
        "PUBLIC_IP": "203.0.113.9",
        "HY2_PORT": "8443",
        "PUBLIC_DOMAIN": "example.test",
        "OBFS_PASSWORD": "obfs-secret",
        "API_SECRET": "api-secret",
        "REALITY_PUBLIC_KEY": "PUBKEY123",
        "REALITY_SHORT_ID": "abcd1234",
        "XRAY_PORT": "8443",
        "PORT_HOP_ENABLED": "true",
        "HY2_PORT_RANGE": "8443-9443",
        "PORT_HOP_INTERVAL": "30",
        "COUNTRY_CODE": "JP",
        "TOTAL_BYTES": "0",
    }
    env.update(over)
    return env


INFO = {"vless_id": "550e8400-e29b-41d4-a716-446655440000", "note": "", "password": "pw", "token": "tk"}


class V2RayBase64Tests(unittest.TestCase):
    """v2rayN 的 SubscriptionHandler 先判 base64 再按行解析链接。"""

    def setUp(self):
        self.ns = load_ns()
        self.raw = self.ns["subscription_base64"](make_env(), "alice", "pw123", INFO)
        self.lines = base64.b64decode(self.raw).decode("utf-8").strip().splitlines()

    def test_decodes_to_lines(self):
        self.assertGreaterEqual(len(self.lines), 1)

    def test_contains_hysteria2_uri(self):
        self.assertTrue(any(l.startswith("hysteria2://") for l in self.lines), self.lines)

    def test_contains_vless_uri(self):
        self.assertTrue(any(l.startswith("vless://") for l in self.lines), self.lines)

    def test_username_password_in_authority(self):
        """userinfo 是 用户名:密码，冒号不能编码成 %3A。

        这条原来断言 "alice%3Apw123@" —— 那是编码后的写法，
        客户端解出来密码为空、认证失败。改成断言字面冒号分隔。
        """
        import urllib.parse
        hy = next(l for l in self.lines if l.startswith("hysteria2://"))
        userinfo = hy.split("//", 1)[1].split("@", 1)[0]
        self.assertIn(":", userinfo)
        self.assertNotIn("%3A", userinfo.upper())
        parsed = urllib.parse.urlsplit(hy)
        self.assertEqual("alice", parsed.username)
        self.assertEqual("pw123", parsed.password)

    def test_same_nodes_as_direct_links(self):
        """必须跟直链完全一致，不能各写一套。"""
        expected = self.ns["direct_links"](make_env(), "alice", "pw123", INFO)
        self.assertEqual(expected, base64.b64decode(self.raw).decode("utf-8"))


class SingBoxTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_ns()
        self.raw = self.ns["subscription_singbox"](make_env(), "alice", "pw123", INFO)
        self.cfg = json.loads(self.raw)

    def test_valid_json(self):
        self.assertIsInstance(self.cfg, dict)

    def test_top_level_sections(self):
        for key in ("log", "dns", "inbounds", "outbounds", "route"):
            self.assertIn(key, self.cfg)

    def test_dns_uses_new_server_format(self):
        """sing-box 1.12 起 DNS server 必须用 type+server，旧 address 写法
        在 1.14 已彻底移除。"""
        servers = self.cfg["dns"]["servers"]
        for s in servers:
            self.assertNotIn("address", s, f"还在用废弃的 address 字段: {s}")
            self.assertIn("type", s)
            if s["type"] in ("https", "tls", "quic", "h3", "udp", "tcp"):
                self.assertIn("server", s)

    def test_no_deprecated_dns_rules(self):
        """dns.rules[].outbound 在 1.12 废弃、1.14 移除。

        ⚠️ 禁的是 `outbound` 这个字段，不是整个 rules。
        rules 本身在 1.12+ 依然是官方推荐的写法（用 `server` 指向 DNS server，
        见 v1.8.6：境外域名走代理 DoH 就靠 dns.rules 分流）。
        以前这里写成 assertNotIn("rules", ...)，属于过度断言。
        """
        for rule in self.cfg["dns"].get("rules", []):
            self.assertNotIn("outbound", rule, f"dns.rules 里不能用 outbound: {rule}")

    def test_route_has_default_domain_resolver(self):
        """替代废弃的 dns.rules[].outbound。"""
        self.assertIn("default_domain_resolver", self.cfg["route"])

    def test_dns_strategy_is_ipv4_only(self):
        """DNS 只解析 IPv4 —— 等价于 Clash 订阅的 ipv6: false。

        真机事故(2026-11-23):WI-Fi 无 IPv6 时,sing-box 把国内域名
        解析成 AAAA(2408:... 联通 v6 段) → 判为国内直连 → direct 经
        wlan0 连 v6 → "network is unreachable",抖音搜索/小红书头像转圈。
        蜂窝有 v6、Clash 有 ipv6:false,所以只有「sing-box + 无 v6 的 WiFi」炸。
        """
        self.assertEqual("ipv4_only", self.cfg["dns"].get("strategy"))

    def test_tun_has_no_ipv6_address(self):
        """tun 不给 IPv6 地址 —— 否则系统以为有 v6,把 v6 包送进 tun
        又被 direct 丢回真实网卡,回到 unreachable 老路。"""
        addr = self.cfg["inbounds"][0]["address"]
        self.assertTrue(any("." in a for a in addr), addr)
        self.assertFalse(any(":" in a for a in addr), addr)

    def test_tun_mtu_is_narrowed(self):
        """tun MTU 显式收窄 —— 默认偏大,撞小 MTU 链路(PPPoE 1492)
        会分片丢包,表现为大图/长页面加载卡。"""
        mtu = self.cfg["inbounds"][0].get("mtu")
        self.assertIsInstance(mtu, int)
        self.assertLessEqual(mtu, 1400)

    def test_hop_interval_has_unit(self):
        """sing-box 要 "30s"，裸数字 "30" 报 missing unit in duration。"""
        hy = self.cfg["outbounds"][0]
        if "hop_interval" in hy:
            self.assertTrue(str(hy["hop_interval"]).endswith("s"), hy["hop_interval"])

    def test_hysteria2_outbound(self):
        hy = self.cfg["outbounds"][0]
        self.assertEqual("hysteria2", hy["type"])
        self.assertEqual("203.0.113.9", hy["server"])

    def test_password_is_userpass_combination(self):
        """sing-box 不认 userpass 别名，必须把 用户名:密码 整个填进 password。

        官方 hysteria2 文档专门警告过这一点，填错会一直认证失败。
        """
        pw = self.cfg["outbounds"][0]["password"]
        self.assertEqual("alice:pw123", pw)

    def test_port_range_uses_colon_form(self):
        """sing-box 的 server_ports 用 起始:结束，不是 Clash 的 起始-结束。"""
        self.assertEqual(["8443:9443"], self.cfg["outbounds"][0]["server_ports"])
        self.assertEqual("30s", str(self.cfg["outbounds"][0]["hop_interval"]))

    def test_single_port_when_hop_disabled(self):
        ns = load_ns()
        cfg = json.loads(ns["subscription_singbox"](make_env(PORT_HOP_ENABLED="false"), "alice", "pw", INFO))
        hy = cfg["outbounds"][0]
        self.assertEqual(8443, hy["server_port"])
        self.assertNotIn("server_ports", hy)

    def test_obfs_block(self):
        obfs = self.cfg["outbounds"][0]["obfs"]
        self.assertEqual("salamander", obfs["type"])

    def test_obfs_absent_when_disabled(self):
        ns = load_ns()
        # obfs_enabled 看的是 OBFS_ENABLED 开关，不是密码是否为空
        cfg = json.loads(
            ns["subscription_singbox"](make_env(OBFS_ENABLED="false"), "alice", "pw", INFO)
        )
        self.assertNotIn("obfs", cfg["outbounds"][0])

    def test_vless_reality_outbound(self):
        vless = next(o for o in self.cfg["outbounds"] if o["type"] == "vless")
        reality = vless["tls"]["reality"]
        self.assertTrue(reality["enabled"])
        self.assertEqual("PUBKEY123", reality["public_key"])
        self.assertEqual("abcd1234", reality["short_id"])
        self.assertEqual("xtls-rprx-vision", vless["flow"])

    def test_selector_groups_all_proxies(self):
        sel = next(o for o in self.cfg["outbounds"] if o["type"] == "selector")
        tags = [o["tag"] for o in self.cfg["outbounds"] if o["type"] in ("hysteria2", "vless")]
        self.assertEqual(tags, sel["outbounds"])

    def test_route_final_is_proxy(self):
        self.assertEqual("proxy", self.cfg["route"]["final"])

    def test_tun_inbound_present(self):
        tun = self.cfg["inbounds"][0]
        self.assertEqual("tun", tun["type"])
        self.assertEqual("mixed", tun.get("stack"))
        self.assertIn("203.0.113.9/32", tun.get("route_exclude_address", []))

    def test_dns_rejects_https_and_svcb_on_112_plus(self):
        rules = self.cfg["dns"]["rules"]
        self.assertTrue(
            any(
                set(r.get("query_type", [])) == {"HTTPS", "SVCB"} and r.get("action") == "reject"
                for r in rules
            )
        )


class FormatSelectionTests(unittest.TestCase):
    """格式优先级：?fmt= 显式 > User-Agent 自动识别。"""

    def setUp(self):
        self.ns = load_ns()
        self.fmt_from_ua = self.ns["subscription_format_from_ua"]
        self.normalize = self.ns["normalize_subscription_format"]

    def test_clash_clients(self):
        for ua in ("clash-verge/2.0", "mihomo/Alpha", "FlClash/0.8", "Stash/2.5"):
            self.assertEqual("clash", self.fmt_from_ua(ua), ua)

    def test_v2ray_clients(self):
        for ua in ("v2rayN/6.0", "v2rayNG/1.8", "Shadowrocket/2.2", "NekoBox/1.0"):
            self.assertEqual("v2ray", self.fmt_from_ua(ua), ua)

    def test_singbox_clients(self):
        for ua in ("sing-box 1.9", "SFA/1.10", "SFI/1.10", "SFM/1.10", "singbox/1.0"):
            self.assertEqual("singbox", self.fmt_from_ua(ua), ua)

    def test_singbox_wins_over_v2ray_substring(self):
        """sing-box 的 UA 里可能夹着别的字样，必须先判它。"""
        self.assertEqual("singbox", self.fmt_from_ua("sing-box/1.9 v2ray-compat"))

    def test_empty_ua_falls_back_to_base64(self):
        """浏览器/curl 拿不到格式线索时给通用 base64，兼容性最好。"""
        self.assertEqual("v2ray", self.fmt_from_ua(""))
        self.assertEqual("v2ray", self.fmt_from_ua("Mozilla/5.0"))

    def test_fmt_aliases(self):
        self.assertEqual("clash", self.normalize("clash"))
        self.assertEqual("clash", self.normalize("yaml"))
        self.assertEqual("clash", self.normalize("meta"))
        self.assertEqual("v2ray", self.normalize("b64"))
        self.assertEqual("v2ray", self.normalize("base64"))
        self.assertEqual("singbox", self.normalize("sb"))
        self.assertEqual("singbox", self.normalize("sing-box"))
        self.assertEqual("singbox", self.normalize("JSON"))

    def test_unknown_fmt_does_not_force(self):
        self.assertEqual("", self.normalize("nonsense"))
        self.assertEqual("", self.normalize(""))


class SubscriptionBodyDispatchTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_ns()

    def test_content_types(self):
        env = make_env()
        _, yaml_ct = self.ns["subscription_body"]("clash", env, "alice", "pw", INFO)
        _, v2_ct = self.ns["subscription_body"]("v2ray", env, "alice", "pw", INFO)
        _, sb_ct = self.ns["subscription_body"]("singbox", env, "alice", "pw", INFO)
        self.assertIn("yaml", yaml_ct)
        self.assertIn("text/plain", v2_ct)
        self.assertIn("json", sb_ct)

    def test_unknown_format_defaults_to_clash(self):
        body, ct = self.ns["subscription_body"]("whatever", make_env(), "alice", "pw", INFO)
        self.assertIn("yaml", ct)
        self.assertIn(b"proxies", body)


class CredentialKindTests(unittest.TestCase):
    """面板按客户端分类复制时，凭据接口要能直接给带 ?fmt= 的链接。"""

    @classmethod
    def setUpClass(cls):
        cls.src = BACKEND.read_text(encoding="utf-8")

    def test_all_three_subscription_kinds_accepted(self):
        for kind in ("subscription", "subscription-v2ray", "subscription-singbox"):
            self.assertIn(kind, self.src)

    def test_v2ray_kind_appends_fmt(self):
        self.assertIn('"subscription-v2ray": "v2ray"', self.src)
        self.assertIn('"subscription-singbox": "singbox"', self.src)


class DefensivePathTests(unittest.TestCase):
    """send_subscription 不能硬依赖 self.path。

    单测里的 stub handler 没有这个属性，真实运行的 HEAD 分支也可能缺。
    用 getattr 兜底，缺了就当成没传 fmt（走 UA 判断）。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = BACKEND.read_text(encoding="utf-8")

    def test_uses_getattr_for_path(self):
        body = self.src[self.src.index("def send_subscription"):]
        body = body[: body.index("def do_HEAD")]
        self.assertIn('getattr(self, "path"', body)




class RealSingboxBinaryTests(unittest.TestCase):
    """用真 sing-box 二进制校验生成的配置。

    纸面推断不够 —— 这套配置连报四个错才修干净：
      legacy DNS server formats（address → type+server）
      hop_interval 缺单位（"30" → "30s"）
      outbound DNS rule item 废弃（dns.rules → route.default_domain_resolver）
    每一条都是 check 出来的，不是看文档猜的。
    """

    BIN_CANDIDATES = (
        "/tmp/sbx/sing-box",
        "sing-box",
    )

    def find_bin(self):
        import shutil
        for cand in self.BIN_CANDIDATES:
            if Path(cand).exists() and Path(cand).is_file():
                return cand
            found = shutil.which(cand)
            if found:
                return found
        return None

    def test_config_passes_check(self):
        import base64
        import subprocess
        bin_path = self.find_bin()
        if not bin_path:
            self.skipTest("sing-box 二进制不可用")
        ns = load_ns()
        env = make_env(REALITY_PUBLIC_KEY=base64.b64encode(bytes(range(32))).decode().rstrip("="))
        body = ns["subscription_singbox"](env, "alice", "pw123", INFO)
        tmp = ROOT / "tests" / ".sb_check.json"
        tmp.write_bytes(body)
        try:
            r = subprocess.run([bin_path, "check", "-c", str(tmp)],
                               capture_output=True, text=True, check=False)
            self.assertEqual(0, r.returncode, f"sing-box 校验失败：{r.stderr[:800]}")
        finally:
            tmp.unlink(missing_ok=True)



class Hy2UriPortTests(unittest.TestCase):
    """HY2 直链的端口跳跃必须走 mport，不能塞进 host:port。

    真机现象：v2ray 扫码后第一个 HY2 节点「没端口没服务器」。
    原因是我们生成 hysteria2://auth@ip:8443-9443/?... ——
    "8443-9443" 不是合法 URI 端口，客户端按 Uri 解析直接失败，
    Address/Port 双双落空。

    依据 2dust/v2rayN ServiceLib/Handler/Fmt/Hysteria2Fmt.cs：
        item.Port = url.Port == -1 ? 443 : url.Port;
        Ports     = GetQueryDecoded(query, "mport");
        dicQuery.Add("mport", Ports.Replace(':', '-'));
    """

    def setUp(self):
        self.ns = load_ns()

    def link(self, hop_enabled: str) -> str:
        env = make_env(PORT_HOP_ENABLED=hop_enabled)
        return self.ns["direct_link"](env, "alice", "pw123")

    def test_port_is_plain_integer(self):
        import urllib.parse
        for hop in ("true", "false"):
            with self.subTest(hop=hop):
                uri = self.link(hop)
                parsed = urllib.parse.urlsplit(uri)
                self.assertIsInstance(parsed.port, int, f"端口解析失败：{uri[:80]}")
                self.assertEqual(8443, parsed.port)

    def test_no_dash_in_authority(self):
        """authority 里出现 - 就说明范围又塞回去了。"""
        uri = self.link("true")
        authority = uri.split("//", 1)[1].split("/", 1)[0]
        self.assertNotIn("-", authority.split("@", 1)[1], authority)

    def test_range_moved_to_mport(self):
        import urllib.parse
        parsed = urllib.parse.urlsplit(self.link("true"))
        q = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(["8443-9443"], q.get("mport"))

    def test_no_mport_when_hop_disabled(self):
        import urllib.parse
        parsed = urllib.parse.urlsplit(self.link("false"))
        q = urllib.parse.parse_qs(parsed.query)
        self.assertNotIn("mport", q)

    def test_clash_yaml_still_uses_ports_field(self):
        """Clash 的写法本来就是对的（port + ports），别被这次改动带坏。"""
        env = make_env()
        yaml_text = self.ns["subscription_yaml"](env, "alice", "pw123", {}).decode()
        self.assertIn("port: 8443", yaml_text)
        self.assertIn("ports:", yaml_text)



class InsecureDefaultTests(unittest.TestCase):
    """只有真的没有可信证书时才该带 insecure / skip-cert-verify。

    真机告警：「将在 2026.8.1 禁用跳过证书验证 allowInsecure，
    请尽快改用证书指纹」。背景是 Clash 系要淘汰 allowInsecure。

    我们原来把 sslip.io 域名一律判成「需要跳过验证」，属于误判：
    sslip.io 是通配 DNS，解析到 IP，但 Caddy 照样能拿到 Let's Encrypt
    正式证书（实测 156-231-141-107.sslip.io 的 issuer 是 Let's Encrypt,
    verify return code 0）。白白关掉证书校验既没必要，又撞上这个弃用警告。
    """

    def setUp(self):
        self.ns = load_ns()
        self.fn = self.ns["client_insecure"]

    def test_sslip_domain_is_secure_by_default(self):
        self.assertFalse(self.fn({
            "DOMAIN": "156-231-141-107.sslip.io",
            "PUBLIC_IP": "156.231.141.107",
        }))

    def test_real_domain_is_secure(self):
        self.assertFalse(self.fn({"DOMAIN": "example.com", "PUBLIC_IP": "1.2.3.4"}))

    def test_bare_ip_needs_insecure(self):
        """Let's Encrypt 签不了裸 IP，这种才必须跳过验证。"""
        self.assertTrue(self.fn({"DOMAIN": "1.2.3.4", "PUBLIC_IP": "1.2.3.4"}))

    def test_empty_domain_is_secure(self):
        self.assertFalse(self.fn({"DOMAIN": "", "PUBLIC_IP": "1.2.3.4"}))

    def test_explicit_override_still_wins(self):
        base = {"DOMAIN": "example.com", "PUBLIC_IP": "1.2.3.4"}
        for value in ("1", "true", "yes", "on"):
            with self.subTest(value=value):
                self.assertTrue(self.fn({**base, "CLIENT_INSECURE": value}))
        for value in ("0", "false", "no", "off"):
            with self.subTest(value=value):
                self.assertFalse(self.fn({**base, "CLIENT_INSECURE": value}))

    def test_yaml_skip_cert_verify_false_for_sslip(self):
        env = make_env(DOMAIN="156-231-141-107.sslip.io", PUBLIC_IP="156.231.141.107")
        yaml_text = self.ns["subscription_yaml"](env, "alice", "pw", {}).decode()
        self.assertIn("skip-cert-verify: false", yaml_text)

    def test_direct_link_has_no_insecure_for_sslip(self):
        env = make_env(DOMAIN="156-231-141-107.sslip.io", PUBLIC_IP="156.231.141.107")
        link = self.ns["direct_link"](env, "alice", "pw")
        self.assertNotIn("insecure", link)



class Hy2UriAuthTests(unittest.TestCase):
    """HY2 直链的 userinfo 里，冒号必须是分隔符，不能编码。

    真机现象：v2ray 客户端里 HY2 节点连不上（Clash 能测延迟）。

    原因：quote(f"{username}:{password}", safe="") 把冒号编成 %3A，
    生成 hysteria2://u%3Ap@host —— 客户端解析时 username 拿到 "u:p"、
    password 为空，认证必然失败。

    Clash 走 YAML 的 password 字段（整串直接给），所以不受影响 ——
    这就是「Clash 能用、v2 不能用」的原因。
    """

    def setUp(self):
        self.ns = load_ns()

    def parse(self, username="alice", password="secret123"):
        import urllib.parse
        link = self.ns["direct_link"](make_env(), username, password)
        return urllib.parse.urlsplit(link)

    def test_username_parsed(self):
        self.assertEqual("alice", self.parse().username)

    def test_password_parsed(self):
        self.assertEqual("secret123", self.parse().password)

    def test_colon_is_literal_separator(self):
        """编码过的 %3A 会让密码解析成 None。"""
        link = self.ns["direct_link"](make_env(), "alice", "pw")
        userinfo = link.split("//", 1)[1].split("@", 1)[0]
        self.assertNotIn("%3A", userinfo.upper(), userinfo)
        self.assertIn(":", userinfo)

    def test_username_needing_encoding(self):
        """用户名含特殊字符时各自编码；客户端解码后能还原。

        注意 urlsplit().username 不做百分号解码（返回 "a%20b"），
        这里按 RFC 3986 自行 unquote 后再比对 —— 客户端也是这么做的。
        """
        import urllib.parse
        parsed = self.parse(username="a b", password="p@ss:w0rd")
        self.assertEqual("a b", urllib.parse.unquote(parsed.username))
        self.assertEqual("p@ss:w0rd", urllib.parse.unquote(parsed.password))

    def test_access_sh_uses_same_rule(self):
        src = (ROOT / "lib" / "access.sh").read_text(encoding="utf-8")
        self.assertIn(chr(34) + ":" + chr(34), src)
        self.assertNotIn(chr(34) + "{username}:{password}" + chr(34) + ", safe=", src)



class SniSelectionTests(unittest.TestCase):
    """订阅里的 SNI 必须跟 Hysteria 实际用的证书对得上。

    真机故障：v2rayNG 报
      "certificate is not valid for any names, but wanted to match www.amazon.sg"
    因为 Hysteria 用的是 openssl 自签证书，SAN 只有 IP，而 SNI 设成了 amazon。

    后来 create_certificate 改成复用 Caddy 的 Let's Encrypt 证书（SAN=DOMAIN），
    所以订阅侧也要跟着用域名当 SNI，客户端才能 insecure=false 通过校验。
    """

    def setUp(self):
        self.ns = load_ns()
        self.fn = self.ns["subscription_sni"]

    def test_domain_wins_over_explicit_sni(self):
        """有域名时优先用域名 —— 证书 SAN 就是它。"""
        got = self.fn({
            "DOMAIN": "156-231-141-107.sslip.io",
            "PUBLIC_IP": "156.231.141.107",
            "SNI": "www.amazon.sg",
        })
        self.assertEqual("156-231-141-107.sslip.io", got)

    def test_bare_ip_falls_back_to_explicit_sni(self):
        got = self.fn({"DOMAIN": "", "PUBLIC_IP": "1.2.3.4", "SNI": "www.amazon.sg"})
        self.assertEqual("www.amazon.sg", got)

    def test_bare_ip_without_explicit_uses_ip(self):
        """自签证书的 SAN 是 IP，所以 SNI 也得是 IP。"""
        got = self.fn({"DOMAIN": "", "PUBLIC_IP": "1.2.3.4", "SNI": ""})
        self.assertEqual("1.2.3.4", got)

    def test_domain_equal_to_ip_treated_as_bare(self):
        got = self.fn({"DOMAIN": "1.2.3.4", "PUBLIC_IP": "1.2.3.4", "SNI": "x.com"})
        self.assertEqual("x.com", got)

    def test_direct_link_uses_it(self):
        env = make_env(DOMAIN="156-231-141-107.sslip.io", PUBLIC_IP="156.231.141.107")
        link = self.ns["direct_link"](env, "alice", "pw")
        self.assertIn("sni=156-231-141-107.sslip.io", link)
        self.assertNotIn("amazon", link)


class CaddyCertReuseTests(unittest.TestCase):
    """create_certificate 要优先复用 Caddy 的 Let's Encrypt 证书。

    原来一律 openssl 自签（SAN 只有 IP），导致所有严格校验的客户端
    只能靠 insecure 硬连。Caddy 那边本来就有真证书。
    """

    @classmethod
    def setUpClass(cls):
        src = (ROOT / "lib" / "cert.sh").read_text(encoding="utf-8")
        cls.src = src
        cls.body = src[src.index("reuse_caddy_certificate()"):]

    def test_helper_defined(self):
        self.assertIn("reuse_caddy_certificate()", self.src)

    def test_tries_both_caddy_layouts(self):
        self.assertIn("/certificates/*/", self.body)
        self.assertIn(".local/share/caddy/certificates", self.body)

    def test_rejects_caddy_local_authority(self):
        """Caddy 自己的本地 CA 不算受信任证书，必须跳过。"""
        self.assertIn("[Cc]addy", self.body)
        self.assertIn("[Aa]uthority", self.body)

    def test_create_prefers_reuse(self):
        body = self.src[self.src.index("create_certificate()"):]
        reuse = body.index("reuse_caddy_certificate")
        sign = body.index("openssl req")
        self.assertLess(reuse, sign, "必须先尝试复用，再退回自签")

    def test_copies_with_correct_ownership(self):
        self.assertIn("hysteria", self.body)
        self.assertIn("-m 0640", self.body)

if __name__ == "__main__":
    unittest.main()

class SingboxChinaSplitTests(unittest.TestCase):
    """sing-box 订阅必须带国内分流,与 Clash 订阅对齐。

    真机 bug:iOS sing-box 导入后微信发不了图片(文本正常)。
    原因:route.rules 只有 ip_is_private → 微信图片上传的国内 CDN
    通道被 tun 全量代理绕道日本 → 失败(sing-box issue #2492,
    社区结论:rule-set 分流让微信直连即解决)。
    """

    @classmethod
    def setUpClass(cls):
        src = (ROOT / "app" / "subscription.py").read_text(encoding="utf-8")
        i = src.index('def subscription_singbox(')
        j = src.index("\ndef subscription_body", i)
        cls.fn = src[i:j]

    def test_has_china_rulesets(self):
        self.assertIn("geosite-cn", self.fn)
        self.assertIn("geoip-cn", self.fn)
        self.assertIn('"type": "remote"', self.fn)

    def test_china_direct_rule(self):
        """国内直连必须是「域名优先、IP 兜底」三条，不能合并成 OR 一条。

        合并成 ["geosite-cn", "geoip-cn"] 时，geoip 命中就直连、域名判断被绕过；
        googlevideo.com（海外域名 + 国内 CDN IP）会被判成直连 → i/o timeout。
        详见 DomainBeforeIpRuleOrderTests。
        """
        self.assertIn('"rule_set": ["geosite-cn"], "outbound": "direct"', self.fn)
        self.assertIn('"rule_set": ["geoip-cn"], "outbound": "direct"', self.fn)
        self.assertNotIn('"rule_set": ["geosite-cn", "geoip-cn"]', self.fn)

    def test_ruleset_download_via_direct(self):
        """1.14+ 默认用顶层 http_clients + dl-direct，1.12~1.13 自动回退 download_detour。"""
        ns = load_ns()
        cfg_114 = json.loads(ns["subscription_singbox"](make_env(), "alice", "pw123", INFO))
        self.assertEqual([{"tag": "dl-direct"}], cfg_114.get("http_clients"))
        for rs in cfg_114["route"]["rule_set"]:
            self.assertEqual("dl-direct", rs.get("http_client"))
            self.assertNotIn("download_detour", rs)
        self.assertNotIn('"http_client": {"detour"', self.fn)

    def test_singbox_version_adaptive_112_and_111(self):
        """1.12~1.13 不能含未知字段 http_clients；1.11 还需回退旧版 DNS server 格式。"""
        ns = load_ns()
        cfg_112 = json.loads(
            ns["subscription_singbox"](
                make_env(), "alice", "pw123", INFO, user_agent="SFI/1.12.10 (1; sing-box 1.12.10)"
            )
        )
        self.assertNotIn("http_clients", cfg_112)
        self.assertEqual("local", cfg_112["route"].get("default_domain_resolver"))
        for rs in cfg_112["route"]["rule_set"]:
            self.assertEqual("direct", rs.get("download_detour"))
            self.assertNotIn("http_client", rs)

        cfg_111 = json.loads(
            ns["subscription_singbox"](
                make_env(), "alice", "pw123", INFO, user_agent="SFA/1.11.4", sbver=""
            )
        )
        self.assertNotIn("http_clients", cfg_111)
        self.assertNotIn("default_domain_resolver", cfg_111["route"])
        self.assertEqual(
            "https://1.1.1.1/dns-query", cfg_111["dns"]["servers"][0].get("address")
        )
        self.assertTrue(
            any(r.get("outbound") == "any" for r in cfg_111["dns"]["rules"])
        )

        # ?sbver= 显式覆盖优先于 UA
        cfg_override = json.loads(
            ns["subscription_singbox"](
                make_env(), "alice", "pw123", INFO, user_agent="sing-box 1.14.4", sbver="1.12"
            )
        )
        self.assertNotIn("http_clients", cfg_override)

    def test_sniff_and_dns_hijack(self):
        """分流依赖域名嗅探;DNS 劫持保证 tun 下解析走 sing-box。"""
        self.assertIn('"action": "sniff"', self.fn)
        self.assertIn('"action": "hijack-dns"', self.fn)

    def test_final_still_proxy(self):
        """被墙流量仍走代理 —— 直连规则只放行国内。"""
        self.assertIn('"final": "proxy"', self.fn)


class SingboxHy2TlsTests(unittest.TestCase):
    """sing-box 订阅的 Hysteria2 TLS 必须走订阅证书体系,不允许硬编码 insecure。

    真机 bug:v2rayNG(安卓)26.2.6+ 弹窗拒绝连接:
      "当前节点使用未加密连接…此类节点无法使用 26.2.6+ 版本的
       Xray 核心连接。如为自建节点,请启用 TLS 等安全加密。"
    原因:sing-box hy2 节点 tls 硬编码 insecure=True,且 SNI 用的是
    REALITY 伪装域名(www.cloudflare.com)—— 与 Hysteria 实际证书
    (Let's Encrypt 签给 DOMAIN)不匹配。Clash 和直链早就是
    subscription_sni + client_insecure 判定,唯独 sing-box 漏改。
    """

    @classmethod
    def setUpClass(cls):
        src = (ROOT / "app" / "subscription.py").read_text(encoding="utf-8")
        i = src.index('def subscription_singbox(')
        j = src.index("\ndef subscription_body", i)
        cls.fn = src[i:j]

    def test_sni_uses_subscription_sni(self):
        """SNI 必须是订阅证书域名,不是 REALITY 伪装域名。"""
        # hy2 节点段里的 server_name
        seg = self.fn[self.fn.index('"type": "hysteria2"'):]
        seg = seg[:seg.index('"type": "vless"')] if '"type": "vless"' in seg else seg
        self.assertIn('"server_name": subscription_sni(env)', seg)
        self.assertNotIn(
            '"server_name": reality_server_name(env)',
            seg,
            "hy2 节点的 SNI 不能用 REALITY 伪装域名",
        )

    def test_insecure_follows_client_insecure(self):
        """insecure 由 client_insecure 判定(有可信证书=False),禁止硬编码。"""
        self.assertIn('"insecure": bool(client_insecure(env))', self.fn)
        self.assertNotIn('"insecure": True', self.fn)

    def test_vless_still_uses_reality_sni(self):
        """VLESS+Reality 节点保留 REALITY 的 SNI(那是 Reality 协议的一部分)。"""
        seg = self.fn[self.fn.index('"type": "vless"'):]
        self.assertIn('"server_name": reality_server_name(env)', seg)


class ProtocolSwitchSubscriptionSyncTests(unittest.TestCase):
    """订阅节点必须联动面板 HY2 / VLESS 开关状态，同时保持纯手动选择模式。"""

    def setUp(self):
        self.ns = load_ns()
        self.env = make_env()

    def test_hy2_off_hides_hy2_and_defaults_to_vless(self):
        import yaml

        sb = json.loads(
            self.ns["subscription_singbox"](
                self.env, "alice", "pw123", INFO, hy2_enabled=False, vless_enabled=True
            )
        )
        types = [o["type"] for o in sb["outbounds"]]
        self.assertNotIn("hysteria2", types)
        self.assertIn("vless", types)
        sel = next(o for o in sb["outbounds"] if o["type"] == "selector")
        self.assertEqual(1, len(sel["outbounds"]))
        self.assertIn("hy2超时备用临时节点", sel["default"])

        clash = yaml.safe_load(
            self.ns["subscription_yaml"](
                self.env, "alice", "pw123", INFO, hy2_enabled=False, vless_enabled=True
            ).decode("utf-8")
        )
        self.assertEqual(["vless"], [p["type"] for p in clash["proxies"]])
        self.assertEqual("select", clash["proxy-groups"][0]["type"])
        self.assertIn("hy2超时备用临时节点", clash["proxy-groups"][0]["proxies"][0])

        b64 = base64.b64decode(
            self.ns["subscription_base64"](
                self.env, "alice", "pw123", INFO, hy2_enabled=False, vless_enabled=True
            )
        ).decode("utf-8")
        self.assertNotIn("hysteria2://", b64)
        self.assertIn("vless://", b64)

    def test_vless_off_hides_vless_node(self):
        import yaml

        sb = json.loads(
            self.ns["subscription_singbox"](
                self.env, "alice", "pw123", INFO, hy2_enabled=True, vless_enabled=False
            )
        )
        types = [o["type"] for o in sb["outbounds"]]
        self.assertIn("hysteria2", types)
        self.assertNotIn("vless", types)

        clash = yaml.safe_load(
            self.ns["subscription_yaml"](
                self.env, "alice", "pw123", INFO, hy2_enabled=True, vless_enabled=False
            ).decode("utf-8")
        )
        self.assertEqual(["hysteria2"], [p["type"] for p in clash["proxies"]])

    def test_both_off_keeps_hy2_fallback_for_valid_config(self):
        sb = json.loads(
            self.ns["subscription_singbox"](
                self.env, "alice", "pw123", INFO, hy2_enabled=False, vless_enabled=False
            )
        )
        sel = next(o for o in sb["outbounds"] if o["type"] == "selector")
        self.assertEqual(1, len(sel["outbounds"]))
        self.assertIn("HY2-alice", sel["default"])
