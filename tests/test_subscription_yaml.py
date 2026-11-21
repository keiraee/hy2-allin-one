import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path


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

    def enable_hop(self, **overrides):
        self.env.update(
            {"PORT_HOP_ENABLED": "true", "PORT_HOP_RANGE": "8443-9443", "PORT_HOP_INTERVAL": "20"}
        )
        self.env.update(overrides)

    def test_port_hop_off_has_no_ports_fields(self):
        text = self.yaml_text()
        self.assertIn("    port: 8443", text)
        self.assertNotIn("ports:", text)
        self.assertNotIn("hop-interval:", text)

    def test_port_hop_adds_ports_and_interval(self):
        self.enable_hop()
        text = self.yaml_text()
        self.assertIn('    ports: "8443-9443"', text)
        self.assertIn("    hop-interval: 20", text)

    def test_port_hop_direct_link_uses_mport_not_authority(self):
        """端口范围不能塞进 host:port。

        这条原来断言的是 ":8443-9443/"，等于把 bug 当成了期望值 ——
        "8443-9443" 不是合法 URI 端口，v2rayN/CMA 解析时 Address 和 Port
        双双落空，真机上表现为「没端口没服务器」。

        正确形态：主端口取区间起点，范围放 mport 查询参数。
        （依据 v2rayN Hysteria2Fmt.cs 的 Parse 分支）
        """
        self.enable_hop()
        text = self.namespace["direct_links"](
            self.env, "alice", "p4ss", {"vless_id": self.vless_id}
        )
        self.assertIn(":8443/?", text)
        self.assertIn("mport=8443-9443", text)
        self.assertNotIn(":8443-9443/", text)

    def test_invalid_hop_range_falls_back_to_single_port(self):
        self.enable_hop(PORT_HOP_RANGE="500-600")
        text = self.yaml_text()
        self.assertNotIn("ports:", text)
        self.assertNotIn("hop-interval:", text)
        links = self.namespace["direct_links"](self.env, "alice", "p4ss")
        self.assertIn(":8443/", links)
        self.assertNotIn(":500-600/", links)

    def test_bad_hop_interval_falls_back_to_30(self):
        self.enable_hop(PORT_HOP_INTERVAL="2")
        text = self.yaml_text()
        self.assertIn("    hop-interval: 30", text)


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

    def test_port_hop_range_in_access_file(self):
        """账号文件里的直链同样不能把范围塞进 host:port。

        这条原来断言 ":8443-9443/" —— 和 backend 那条一样，把 bug 固化成了
        期望值。真正的形态：主端口是区间起点，范围在 mport 参数里。
        """
        text = self.render_access(
            extra_env="PORT_HOP_ENABLED=true\nPORT_HOP_RANGE=8443-9443\n"
        )
        # 人读的那行保留范围（那是给人看的说明，不是 URI）
        self.assertIn("HY2 端口：8443-9443/UDP（端口跳跃）", text)
        # 但 URI 必须是合法端口 + mport
        self.assertIn(":8443/?", text)
        self.assertIn("mport=8443-9443", text)
        self.assertNotIn(":8443-9443/", text)

    def test_invalid_hop_range_falls_back_in_access_file(self):
        text = self.render_access(
            extra_env="PORT_HOP_ENABLED=true\nPORT_HOP_RANGE=500-600\n"
        )
        self.assertIn("HY2 端口：8443/UDP", text)
        self.assertNotIn(":500-600/", text)


if __name__ == "__main__":
    unittest.main()


class ClashDnsSplitTests(unittest.TestCase):
    """Clash DNS 必须国内优先 —— 否则国内 CDN 被解析到国外节点。

    真机现象(小k,2026-11-21):电脑版 Clash 走规则或全局模式,
    抖音店铺都变慢。根因不是分流规则(rules 是对的),而是 DNS:
    fake-ip 模式下所有域名用 1.1.1.1/8.8.8.8(全国外)解析,
    抖音 CDN 按解析者位置调度 → 拿到国外/异常节点 → 国内直连绕远。
    """

    @classmethod
    def setUpClass(cls):
        src = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        i = src.index("dns:\n  enable: true")
        cls.dns = src[i : src.index("proxies:", i)]

    def test_default_nameservers_are_domestic(self):
        """默认 nameserver 必须是国内 DNS(阿里/腾讯)。"""
        self.assertIn("223.5.5.5", self.dns)
        self.assertIn("119.29.29.29", self.dns)
        # 默认列表里不能是纯国外 DNS(1.1.1.1 只允许出现在 policy 里)
        ns_block = self.dns[self.dns.index("nameserver:"):self.dns.index("nameserver-policy")]
        self.assertNotIn("1.1.1.1", ns_block, "默认 nameserver 不能用国外 DNS")

    def test_blocked_domains_use_foreign_doh(self):
        """被墙域名走国外 DoH(否则污染 IP 走代理连不上)。"""
        self.assertIn("nameserver-policy", self.dns)
        self.assertIn("geosite:geolocation-!cn", self.dns)
        policy = self.dns[self.dns.index("nameserver-policy"):]
        self.assertIn("https://1.1.1.1/dns-query", policy)

    def test_proxy_server_domain_resolution(self):
        """自定义节点域名解析走国外 DoH。"""
        self.assertIn("proxy-server-nameserver", self.dns)

    def test_fake_ip_range_explicit(self):
        self.assertIn("fake-ip-range", self.dns)

    def test_ipv6_still_disabled(self):
        self.assertIn("ipv6: false", self.dns)
