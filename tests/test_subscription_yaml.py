import io
import json
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


if __name__ == "__main__":
    unittest.main()
