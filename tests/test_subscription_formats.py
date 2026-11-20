"""多客户端订阅：Clash YAML / v2ray base64 / sing-box JSON。

三份内容必须描述同一批节点 —— 分叉成两套实现迟早会出现
「Clash 能连、v2ray 连不上」这种查半天的问题。
"""

import base64
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "lib" / "backend.sh"


def load_ns():
    src = BACKEND.read_text(encoding="utf-8")
    start = "#!/usr/bin/env python3"
    i = src.index(start)
    j = src.index("\nPY\n", i)
    ns = {"__name__": "hy2_sub_test"}
    exec(compile(src[i:j], "server.py", "exec"), ns)
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
        hy = next(l for l in self.lines if l.startswith("hysteria2://"))
        self.assertIn("alice%3Apw123@", hy)

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
        """dns.rules[].outbound 在 1.12 废弃、1.14 移除。"""
        self.assertNotIn("rules", self.cfg["dns"])

    def test_route_has_default_domain_resolver(self):
        """替代废弃的 dns.rules[].outbound。"""
        self.assertIn("default_domain_resolver", self.cfg["route"])

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
        self.assertEqual("tun", self.cfg["inbounds"][0]["type"])


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

if __name__ == "__main__":
    unittest.main()