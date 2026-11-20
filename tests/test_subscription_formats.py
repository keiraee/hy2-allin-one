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
        self.assertEqual("30", str(self.cfg["outbounds"][0]["hop_interval"]))

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


if __name__ == "__main__":
    unittest.main()