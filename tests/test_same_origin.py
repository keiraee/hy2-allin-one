import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_same_origin_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class StubHandler:
    def __init__(self, headers):
        self.headers = headers
        self.responses = []

    def send_json(self, status, payload):
        self.responses.append((status, payload))


class SameOriginTests(unittest.TestCase):
    panel_domain = "panel.example.com"
    panel_port = "8443"

    def setUp(self):
        self.ns = load_backend_namespace()
        self.ns["load_env"] = lambda: {
            "DOMAIN": self.panel_domain,
            "PANEL_PORT": self.panel_port,
        }

    def check(self, headers):
        stub = StubHandler(headers)
        allowed = self.ns["Handler"].require_same_origin(stub)
        return allowed, stub.responses

    def test_origin_null_is_rejected(self):
        # 沙箱 iframe / data: / file:// 的表单与 fetch 会带 Origin: null，
        # 不应凭它绕过同源校验（配合浏览器缓存的 Basic Auth 即可 CSRF）。
        allowed, responses = self.check({"Origin": "null"})
        self.assertFalse(allowed)
        self.assertEqual(403, responses[0][0])

    def test_cross_site_origin_is_rejected(self):
        allowed, responses = self.check({"Origin": "https://evil.example.com"})
        self.assertFalse(allowed)
        self.assertEqual(403, responses[0][0])

    def test_matching_origin_and_panel_port_is_allowed(self):
        allowed, _ = self.check({"Origin": "https://panel.example.com:8443"})
        self.assertTrue(allowed)

    def test_implicit_default_port_origin_is_not_enough_for_custom_panel_port(self):
        # 面板在 8443 时，来源 https://panel.example.com（隐含 443）是另一个端口的应用，
        # 不能因为"域名对上"就当同源。
        allowed, responses = self.check({"Origin": "https://panel.example.com"})
        self.assertFalse(allowed)
        self.assertEqual(403, responses[0][0])

    def test_implicit_default_port_origin_allowed_when_panel_uses_443(self):
        self.panel_port = "443"
        allowed, _ = self.check({"Origin": "https://panel.example.com"})
        self.assertTrue(allowed)

    def test_missing_origin_and_referer_is_allowed_for_cli(self):
        # hy2 sync / 安装脚本经 api_post 直连后端，不带 Origin/Referer。
        allowed, _ = self.check({})
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
