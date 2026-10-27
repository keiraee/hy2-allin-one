import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

try:
    import yaml
except ImportError:  # 未装 PyYAML 时相关用例自行 skipTest
    yaml = None


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_subscription_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class SubscriptionYamlTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.namespace["server_country_code"] = lambda env: ""  # 本组用例不测国旗
        self.temporary = tempfile.TemporaryDirectory()
        self.mode_file = Path(self.temporary.name) / "client-mode.json"
        self.mode_file.write_text("{}\n", encoding="utf-8")
        self.namespace["MODE_FILE"] = self.mode_file
        self.env = {
            "PUBLIC_IP": "203.0.113.10",
            "HY2_PORT": "8443",
            "XRAY_PORT": "8443",
            "OBFS_ENABLED": "true",
            "OBFS_PASSWORD": "obfs-secret",
            "SNI": "www.amazon.sg",
            "CLIENT_INSECURE": "true",
            "DOMAIN": "203-0-113-10.sslip.io",
            "REALITY_PUBLIC_KEY": "public-key-fixture",
            "REALITY_SHORT_ID": "abcd1234",
            "REALITY_DEST": "www.cloudflare.com:443",
            "REALITY_SERVER_NAMES": "www.cloudflare.com",
        }
        self.vless_id = "11111111-2222-4333-8444-555555555555"

    def tearDown(self):
        self.temporary.cleanup()

    def yaml_text(self, username="alice", password="p4ss", **mode):
        if mode:
            self.mode_file.write_text(json.dumps({"default": mode}), encoding="utf-8")
        body = self.namespace["subscription_yaml"](
            self.env, username, password, {"vless_id": self.vless_id}
        )
        return body.decode("utf-8")

    def test_uses_rule_mode_not_global(self):
        text = self.yaml_text()
        self.assertRegex(text, r"(?m)^mode: rule$")
        self.assertNotRegex(text, r"(?m)^mode: global$")
        self.assertNotIn('name: "GLOBAL"', text)

    def test_proxy_group_selects_node_or_direct(self):
        text = self.yaml_text()
        self.assertIn("name: PROXY", text)
        self.assertIn('"HY2-alice"', text)
        self.assertIn('"hy2超时备用临时节点"', text)
        self.assertIn("type: vless", text)
        self.assertIn("flow: xtls-rprx-vision", text)
        self.assertIn("reality-opts:", text)
        self.assertIn("- DIRECT", text)
        self.assertIn("- MATCH,PROXY", text)

    def test_embeds_blackmatrix7_china_domain_and_metcube_cn_ip(self):
        text = self.yaml_text()
        self.assertIn("rule-providers:", text)
        self.assertIn("china-domain:", text)
        self.assertIn("behavior: domain", text)
        self.assertIn(
            "https://testingcf.jsdelivr.net/gh/blackmatrix7/ios_rule_script@master/rule/Clash/China/China_Domain.yaml",
            text,
        )
        self.assertIn("china-ip:", text)
        self.assertIn("behavior: ipcidr", text)
        self.assertIn("format: mrs", text)
        self.assertIn(
            "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geoip/cn.mrs",
            text,
        )
        self.assertIn("- RULE-SET,china-domain,DIRECT", text)
        self.assertIn("- RULE-SET,china-ip,DIRECT", text)
        self.assertIn("- IP-CIDR,192.168.0.0/16,DIRECT,no-resolve", text)

    def test_keeps_tun_dns_node_and_obfs(self):
        text = self.yaml_text()
        self.assertIn("tun:", text)
        self.assertIn("auto-route: true", text)
        self.assertIn('"203.0.113.10/32"', text)
        self.assertIn("dns:", text)
        self.assertIn("type: hysteria2", text)
        self.assertIn("obfs: salamander", text)
        self.assertIn("keepalive: 5s", text)

    def test_vless_share_link_uses_reality_query(self):
        link = self.namespace["vless_link"](
            self.env, "alice", {"vless_id": self.vless_id}
        )
        self.assertTrue(link.startswith("vless://11111111-2222-4333-8444-555555555555@203.0.113.10:8443?"))
        self.assertIn("security=reality", link)
        self.assertIn("flow=xtls-rprx-vision", link)
        self.assertIn("sni=www.cloudflare.com", link)
        self.assertIn("pbk=public-key-fixture", link)
        self.assertIn("sid=abcd1234", link)
        self.assertIn("#" + urllib.parse.quote("hy2超时备用临时节点", safe=""), link)
        self.assertEqual(self.namespace["VLESS_NODE_NAME"], "hy2超时备用临时节点")
        access = (ROOT / "lib" / "access.sh").read_text(encoding="utf-8")
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn(self.namespace["VLESS_NODE_NAME"], access)
        self.assertNotIn('f"VLESS-{username}"', access)
        self.assertNotIn('q("VLESS-" + username)', backend)
        self.assertNotIn('"VLESS-alice"', self.yaml_text())

    def test_direct_links_are_two_lines(self):
        text = self.namespace["direct_links"](
            self.env, "alice", "p4ss", {"vless_id": self.vless_id}
        )
        lines = text.splitlines()
        self.assertEqual(2, len(lines))
        self.assertTrue(lines[0].startswith("hysteria2://"))
        self.assertTrue(lines[1].startswith("vless://"))

    def test_brutal_mode_still_writes_rate_lines(self):
        text = self.yaml_text(mode="brutal", up_mbps=80, down_mbps=300)
        self.assertIn('up: "80 Mbps"', text)
        self.assertIn('down: "300 Mbps"', text)
        self.assertRegex(text, r"(?m)^mode: rule$")


class AdblockRuleTests(unittest.TestCase):
    """去广告规则集：默认开启、可关闭、两档规则源，且必须排在 china-domain 之前。"""

    def setUp(self):
        self.namespace = load_backend_namespace()
        self.namespace["server_country_code"] = lambda env: ""
        self.temporary = tempfile.TemporaryDirectory()
        self.mode_file = Path(self.temporary.name) / "client-mode.json"
        self.mode_file.write_text("{}\n", encoding="utf-8")
        self.namespace["MODE_FILE"] = self.mode_file
        self.base_env = {
            "PUBLIC_IP": "203.0.113.10",
            "HY2_PORT": "8443",
            "XRAY_PORT": "8443",
            "OBFS_ENABLED": "false",
            "SNI": "www.amazon.sg",
            "CLIENT_INSECURE": "true",
            "DOMAIN": "203-0-113-10.sslip.io",
        }
        self.info = {"vless_id": "11111111-2222-4333-8444-555555555555"}

    def tearDown(self):
        self.temporary.cleanup()

    def text(self, **extra):
        env = dict(self.base_env)
        env.update(extra)
        return self.namespace["subscription_yaml"](env, "alice", "p4ss", self.info).decode(
            "utf-8"
        )

    def test_enabled_by_default_with_lite_ruleset(self):
        text = self.text()
        self.assertIn("  adblock:\n", text)
        self.assertIn("behavior: classical", text)
        self.assertIn("ACL4SSR/ACL4SSR@master/Clash/BanAD.list", text)
        self.assertIn("- RULE-SET,adblock,REJECT", text)

    def test_rule_sources_avoid_raw_github(self):
        """规则由客户端去拉；raw.githubusercontent 在国内基本拉不动，拉不到就静默没有去广告。"""
        for text in (self.text(), self.text(ADBLOCK_LEVEL="full")):
            self.assertNotIn("raw.githubusercontent.com", text)
            self.assertIn("testingcf.jsdelivr.net", text)

    def test_lite_ruleset_declares_text_format(self):
        """BanAD.list 是纯文本；标成 yaml 内核会按 payload: 解析出 0 条，去广告静默失效。"""
        if yaml is None:
            self.skipTest("未安装 PyYAML")
        provider = yaml.safe_load(self.text())["rule-providers"]["adblock"]
        self.assertEqual("text", provider["format"])
        self.assertTrue(str(provider["path"]).endswith(".list"))

    def test_levels_use_separate_cache_files(self):
        """两档同用一个缓存路径，切档后内核会拿上一档的残留文件解析出新格式的 0 条。"""
        if yaml is None:
            self.skipTest("未安装 PyYAML")
        lite = yaml.safe_load(self.text())["rule-providers"]["adblock"]
        full = yaml.safe_load(self.text(ADBLOCK_LEVEL="full"))["rule-providers"]["adblock"]
        self.assertNotEqual(lite["path"], full["path"])
        self.assertEqual("text", lite["format"])
        self.assertEqual("yaml", full["format"])

    def test_can_be_disabled(self):
        text = self.text(ADBLOCK_ENABLED="false")
        self.assertNotIn("adblock", text)
        self.assertNotIn("RULE-SET,adblock", text)
        # 关闭后国内分流与兜底仍然完整
        self.assertIn("- RULE-SET,china-domain,DIRECT", text)
        self.assertIn("- MATCH,PROXY", text)

    def test_full_level_switches_source_and_slows_interval(self):
        text = self.text(ADBLOCK_LEVEL="full")
        self.assertIn("Advertising/Advertising_Classical.yaml", text)
        self.assertIn("interval: 604800", text)
        self.assertNotIn("BanAD.list", text)

    def test_unknown_level_falls_back_to_lite(self):
        text = self.text(ADBLOCK_LEVEL="banana")
        self.assertIn("BanAD.list", text)
        self.assertIn("interval: 86400", text)

    def test_adblock_rule_precedes_china_domain(self):
        """广告域名可能挂在 .cn / 国内 CDN 上，必须先于 china-domain 命中，否则会被 DIRECT 放行。"""
        text = self.text()
        ad_index = text.index("- RULE-SET,adblock,REJECT")
        china_index = text.index("- RULE-SET,china-domain,DIRECT")
        self.assertLess(ad_index, china_index)

    def test_lan_and_private_cidrs_stay_ahead_of_adblock(self):
        """内网直连必须排最前，去广告不能把它们抢走。"""
        text = self.text()
        ad_index = text.index("- RULE-SET,adblock,REJECT")
        lan_index = text.index("- IP-CIDR,192.168.0.0/16,DIRECT,no-resolve")
        self.assertLess(lan_index, ad_index)

    def test_generated_yaml_parses(self):
        """结构正确性：payload 缩进、段落边界都不能破坏 YAML。"""
        try:
            import yaml
        except ImportError:
            self.skipTest("未安装 PyYAML")
        data = yaml.safe_load(self.text())
        self.assertIn("adblock", data["rule-providers"])
        self.assertEqual("classical", data["rule-providers"]["adblock"]["behavior"])
        self.assertIn("RULE-SET,adblock,REJECT", data["rules"])
        self.assertEqual("MATCH,PROXY", data["rules"][-1])


class SubscriptionUserinfoTests(unittest.TestCase):
    """订阅头命名与全站约定对齐：upload 对应 tx（Hysteria 口径 tx=客户端上行）。"""

    class StubHandler:
        def __init__(self):
            self.command = "GET"
            self.headers = {}
            self.status = None
            self.header_pairs = []
            self.wfile = io.BytesIO()

        def require_rate_limit(self, *_args):
            return True

        def send_response(self, status, *_args):
            self.status = status

        def send_header(self, key, value):
            self.header_pairs.append((key, value))

        def end_headers(self):
            pass

        def send_error(self, status, *_args):
            self.status = status

        def send_json(self, status, payload):
            self.status = status

    def setUp(self):
        self.namespace = load_backend_namespace()
        self.namespace["server_country_code"] = lambda env: ""  # 本组用例不测国旗
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.namespace["MODE_FILE"] = root / "client-mode.json"
        self.namespace["DATA_FILE"] = root / "data.json"
        self.env = {
            "PUBLIC_IP": "203.0.113.10",
            "HY2_PORT": "8443",
            "OBFS_ENABLED": "false",
            "SNI": "www.amazon.sg",
            "DOMAIN": "panel.example.com",
            "PANEL_PORT": "443",
        }
        self.namespace["load_env"] = lambda: dict(self.env)
        self.namespace["load_users"] = lambda: {
            "alice": {"password": "pw", "token": "tok", "disabled": False}
        }

        def fake_read_json(path, default):
            if path == self.namespace["DATA_FILE"]:
                return {"server": {"traffic": {"rx": 111, "tx": 222, "limit": 999}}}
            return default

        self.namespace["read_json"] = fake_read_json

    def tearDown(self):
        self.temporary.cleanup()

    def test_userinfo_upload_column_follows_tx_convention(self):
        stub = self.StubHandler()
        self.namespace["Handler"].send_subscription(stub, "tok")
        self.assertEqual(200, stub.status)
        userinfo = [value for key, value in stub.header_pairs if key == "Subscription-Userinfo"]
        self.assertEqual(1, len(userinfo))
        self.assertIn("upload=222; download=111", userinfo[0])
        self.assertIn("total=999", userinfo[0])

    def test_content_disposition_no_quotes_no_extension(self):
        stub = self.StubHandler()
        self.namespace["Handler"].send_subscription(stub, "tok")
        disposition = [v for k, v in stub.header_pairs if k == "Content-Disposition"]
        self.assertEqual(1, len(disposition))
        self.assertEqual("attachment; filename=HY2-alice", disposition[0])


class SubscriptionFlagTests(unittest.TestCase):
    """节点名加国旗：COUNTRY_CODE 覆盖或按 PUBLIC_IP 自动查归属地。"""

    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.mode_file = Path(self.temporary.name) / "client-mode.json"
        self.mode_file.write_text("{}\n", encoding="utf-8")
        self.namespace["MODE_FILE"] = self.mode_file
        self.env = {
            "PUBLIC_IP": "203.0.113.10",
            "HY2_PORT": "8443",
            "XRAY_PORT": "8443",
            "OBFS_ENABLED": "false",
            "SNI": "www.amazon.sg",
            "CLIENT_INSECURE": "true",
            "DOMAIN": "203-0-113-10.sslip.io",
            "REALITY_PUBLIC_KEY": "public-key-fixture",
            "REALITY_SHORT_ID": "abcd1234",
            "REALITY_DEST": "www.cloudflare.com:443",
            "REALITY_SERVER_NAMES": "www.cloudflare.com",
        }
        self.vless_id = "11111111-2222-4333-8444-555555555555"

    def tearDown(self):
        self.temporary.cleanup()

    def test_country_code_to_flag(self):
        to_flag = self.namespace["country_code_to_flag"]
        self.assertEqual("🇸🇬", to_flag("SG"))
        self.assertEqual("🇺🇸", to_flag("us"))
        self.assertEqual("", to_flag(""))
        self.assertEqual("", to_flag("X"))
        self.assertEqual("", to_flag("SGP"))

    def test_country_code_override_prefixes_names(self):
        self.env["COUNTRY_CODE"] = "SG"
        text = self.namespace["subscription_yaml"](
            self.env, "alice", "p4ss", {"vless_id": self.vless_id}
        ).decode("utf-8")
        self.assertIn('"🇸🇬 HY2-alice"', text)
        self.assertIn('"🇸🇬 hy2超时备用临时节点"', text)

        links = self.namespace["direct_links"](
            self.env, "alice", "p4ss", {"vless_id": self.vless_id}
        )
        self.assertIn("#" + urllib.parse.quote("🇸🇬 HY2-alice", safe=""), links)
        self.assertIn(
            "#" + urllib.parse.quote("🇸🇬 hy2超时备用临时节点", safe=""), links
        )

    def test_auto_lookup_caches_result(self):
        calls = []

        def fake_json(url):
            calls.append(url)
            return {"country_code": "jp"}

        self.namespace["_http_get_json"] = fake_json
        code = self.namespace["server_country_code"](self.env)
        self.assertEqual("JP", code)
        self.assertEqual("JP", self.namespace["server_country_code"](self.env))
        self.assertEqual(1, len(calls))

        text = self.namespace["subscription_yaml"](
            self.env, "alice", "p4ss", {"vless_id": self.vless_id}
        ).decode("utf-8")
        self.assertIn('"🇯🇵 HY2-alice"', text)

    def test_lookup_failure_is_retried_after_window(self):
        """查不到若被永久缓存，一次网络抖动就让国旗一直不出现，只能重启后端。"""
        calls = []

        def always_fail(url):
            calls.append(url)
            return None

        self.namespace["_http_get_json"] = always_fail
        self.assertEqual("", self.namespace["server_country_code"](self.env))
        self.assertEqual(3, len(calls))
        # 窗口内拿缓存，不再空跑 3 次超时
        self.assertEqual("", self.namespace["server_country_code"](self.env))
        self.assertEqual(3, len(calls))
        # 时间戳放到窗口之外后重试，这次通了
        self.namespace["_GEO_CACHE"]["203.0.113.10"] = ("", 0.0)
        self.namespace["_http_get_json"] = lambda url: {"country_code": "sg"}
        self.assertEqual("SG", self.namespace["server_country_code"](self.env))

    def test_lookup_failure_keeps_original_names(self):
        self.namespace["_http_get_json"] = lambda url: None
        text = self.namespace["subscription_yaml"](
            self.env, "alice", "p4ss", {"vless_id": self.vless_id}
        ).decode("utf-8")
        self.assertIn('"HY2-alice"', text)
        self.assertIn('"hy2超时备用临时节点"', text)


class AccessFileFlagTests(unittest.TestCase):
    """访问资料文件里的节点名必须和面板/订阅一模一样（hy2 show 直接打印它）。"""

    def render_access(self, extra_env="", data_json=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "config.env"
            users_file = root / "users.json"
            mode_file = root / "client-mode.json"
            out_file = root / "access.txt"
            data_file = root / "data.json"
            env_file.write_text(
                "DOMAIN=panel.example.com\nPANEL_PORT=443\nPANEL_PATH=p\n"
                "PANEL_USER=admin\nPANEL_PASS=secret\nAIO_VERSION=9.9.9\n"
                "PUBLIC_IP=203.0.113.10\nHY2_PORT=8443\nSNI=www.amazon.sg\n"
                "OBFS_ENABLED=false\nTOTAL_BYTES=0\n"
                "REALITY_PUBLIC_KEY=public-key-fixture\nREALITY_SHORT_ID=abcd1234\n"
                "REALITY_DEST=www.cloudflare.com:443\n"
                "REALITY_SERVER_NAMES=www.cloudflare.com\n" + extra_env,
                encoding="utf-8",
            )
            users_file.write_text(
                json.dumps(
                    {
                        "alice": {
                            "password": "pw",
                            "token": "tok",
                            "disabled": False,
                            "vless_id": "11111111-2222-4333-8444-555555555555",
                        }
                    }
                ),
                encoding="utf-8",
            )
            mode_file.write_text("{}", encoding="utf-8")
            if data_json is not None:
                data_file.write_text(data_json, encoding="utf-8")
            source = (ROOT / "lib" / "access.sh").read_text(encoding="utf-8")
            start = source.index("<<'PY'\n") + len("<<'PY'\n")
            body = source[start : source.index("\nPY\n", start)]
            argv = sys.argv
            argv_list = [
                "access",
                str(env_file),
                str(users_file),
                str(mode_file),
                str(out_file),
                str(data_file),
            ]
            sys.argv = argv_list
            try:
                exec(compile(body, "access.py", "exec"), {"__name__": "access_test"})
            finally:
                sys.argv = argv
            return out_file.read_text(encoding="utf-8")

    def test_flag_comes_from_backend_resolved_country(self):
        text = self.render_access(data_json='{"server": {"country_code": "SG"}}')
        self.assertIn("#" + urllib.parse.quote("🇸🇬 HY2-alice", safe=""), text)
        self.assertIn("#" + urllib.parse.quote("🇸🇬 hy2超时备用临时节点", safe=""), text)

    def test_no_country_keeps_original_names(self):
        for data_json in (None, "{}", '{"server": {}}', "{not json"):
            text = self.render_access(data_json=data_json)
            self.assertIn("#" + urllib.parse.quote("HY2-alice", safe=""), text)
            self.assertNotIn("🇸🇬", text)

    def test_config_env_override_wins(self):
        text = self.render_access(
            extra_env="COUNTRY_CODE=us\n", data_json='{"server": {"country_code": "SG"}}'
        )
        self.assertIn("#" + urllib.parse.quote("🇺🇸 HY2-alice", safe=""), text)


if __name__ == "__main__":
    unittest.main()
