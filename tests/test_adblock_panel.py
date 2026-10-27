import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_adblock_panel_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class AdblockSettingsTests(unittest.TestCase):
    """面板开关：config.env 是 root:hy2-aio 0640、面板用户写不了，
    所以覆盖值落在单独的 adblock.json 上，并且优先于 config.env。"""

    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.settings = Path(self.temporary.name) / "adblock.json"
        self.namespace["ADBLOCK_FILE"] = self.settings
        self.env = {"ADBLOCK_ENABLED": "true", "ADBLOCK_LEVEL": "lite"}

    def tearDown(self):
        self.temporary.cleanup()

    def test_falls_back_to_config_env_when_file_missing(self):
        self.assertTrue(self.namespace["adblock_enabled"](self.env))
        self.assertEqual("lite", self.namespace["adblock_level"](self.env))
        self.assertEqual(
            "full",
            self.namespace["adblock_level"](dict(self.env, ADBLOCK_LEVEL="full")),
        )

    def test_panel_override_beats_config_env(self):
        self.namespace["save_adblock_settings"](False, "full")
        self.assertFalse(self.namespace["adblock_enabled"](self.env))
        self.assertEqual("full", self.namespace["adblock_level"](self.env))

    def test_partial_write_keeps_other_field(self):
        self.namespace["save_adblock_settings"](False, "full")
        state = self.namespace["save_adblock_settings"](True, None)
        self.assertTrue(state["enabled"])
        self.assertEqual("full", state["level"])

    def test_rejects_unknown_level(self):
        with self.assertRaises(ValueError):
            self.namespace["save_adblock_settings"](None, "banana")
        self.assertFalse(self.settings.exists())

    def test_corrupt_file_does_not_break_subscription(self):
        # 半截 JSON 不能让整个订阅 500。
        self.settings.write_text("{not json", encoding="utf-8")
        self.assertTrue(self.namespace["adblock_enabled"](self.env))
        self.assertEqual("lite", self.namespace["adblock_level"](self.env))

    def test_settings_file_is_group_readable_not_world_readable(self):
        if os.name != "posix":
            self.skipTest("POSIX 权限位断言只在 Linux 上有意义")
        self.namespace["save_adblock_settings"](True, "lite")
        self.assertEqual(0o640, self.settings.stat().st_mode & 0o777)


class AdblockApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.settings = Path(self.temporary.name) / "adblock.json"
        self.namespace["ADBLOCK_FILE"] = self.settings
        self.namespace["load_env"] = lambda: {"ADBLOCK_ENABLED": "true", "ADBLOCK_LEVEL": "lite"}
        self.collect_calls = []
        namespace = self.namespace

        def fake_collect(*_args, **_kwargs):
            # 面板读的是采集器写的 data.json，路由必须当场重采一次。
            self.collect_calls.append(1)
            return {
                "server": {
                    "adblock": {
                        "enabled": namespace["adblock_enabled"]({}),
                        "level": namespace["adblock_level"]({}),
                    }
                }
            }

        self.namespace["collect"] = fake_collect

    def tearDown(self):
        self.temporary.cleanup()

    class FakeRequest:
        def __init__(self, body, path="/adblock"):
            self.path = path
            self.body = body
            self.headers = {"Content-Type": "application/json"}
            self.response = None
            self.command = "POST"

        def require_api_secret(self):
            return True

        def require_same_origin(self):
            return True

        def require_rate_limit(self, *_args):
            return True

        def read_body(self):
            return self.body

        def send_json(self, status, payload):
            self.response = (status, payload)

    def post(self, body):
        request = self.FakeRequest(body)
        self.namespace["Handler"].do_POST(request)
        return request.response

    def test_toggle_off(self):
        status, payload = self.post({"enabled": False})
        self.assertEqual(200, status, payload)
        self.assertFalse(payload["adblock"]["enabled"])

    def test_switch_level(self):
        status, payload = self.post({"level": "full"})
        self.assertEqual(200, status, payload)
        self.assertEqual("full", payload["adblock"]["level"])

    def test_route_refreshes_panel_data_json(self):
        """不重采的话，面板紧跟着的 load() 会读到 60 秒前的旧开关值并把它掰回去。"""
        self.post({"enabled": False})
        self.assertEqual(1, len(self.collect_calls))

    def test_rejects_non_bool_enabled(self):
        status, payload = self.post({"enabled": "false"})
        self.assertEqual(400, status, payload)

    def test_rejects_bad_level(self):
        status, payload = self.post({"level": "banana"})
        self.assertEqual(400, status, payload)


class AdblockPanelMarkupTests(unittest.TestCase):
    def setUp(self):
        self.panel = (ROOT / "lib" / "panel.sh").read_text(encoding="utf-8")

    def test_panel_exposes_adblock_controls(self):
        self.assertIn('id="adblockToggle"', self.panel)
        self.assertIn('id="adblockLevel"', self.panel)
        self.assertIn("api/adblock", self.panel)

    def test_panel_binds_adblock_handlers(self):
        self.assertIn('$("adblockToggle").onclick=toggleAdblock;', self.panel)
        self.assertIn('$("adblockLevel").onchange=changeAdblockLevel;', self.panel)

    def test_panel_renders_server_adblock_state(self):
        self.assertIn("renderAdblock(data.server.adblock", self.panel)


class CliOverrideTests(unittest.TestCase):
    """命令行是 root 的显式指令，必须能盖掉面板写下的覆盖值。"""

    def test_cli_clears_panel_override_before_writing(self):
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        body = config[config.index("adblock_cmd() {"):]
        body = body[: body.index("\n}\n")]
        for branch in ("on|enable)", "off|disable)", "lite|full)"):
            self.assertIn(branch, body)
        self.assertEqual(3, body.count("adblock_clear_panel_override\n"))


if __name__ == "__main__":
    unittest.main()
