"""VLESS (Xray) switch tests: panel toggle, backend routes, flag file, and systemd guard."""

import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    source = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
    namespace = {"__name__": "hy2_aio_vless_switch_test"}
    exec(compile(source, "server.py", "exec"), namespace)
    return namespace


class VlessSwitchTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.off_file = self.root / "xray.off"
        self.users_file = self.root / "users.json"
        self.users_file.write_text(
            json.dumps(
                {
                    "alice": {
                        "password": "pw",
                        "vless_id": "11111111-2222-4333-8444-555555555555",
                        "disabled": False,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.namespace["XRAY_OFF_FILE"] = self.off_file
        self.namespace["USERS_FILE"] = self.users_file
        self.namespace["XRAY_REBUILD_FILE"] = self.root / "rebuild_xray.py"
        (self.root / "rebuild_xray.py").write_text("# stub\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_panel_and_backend_wire_vless_toggle(self):
        panel = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        backend = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")

        self.assertIn('id="vlessToggle"', panel)
        self.assertIn('id="vlessOffBanner"', panel)
        self.assertIn("api/vless/off", panel)
        self.assertIn("api/vless/on", panel)
        self.assertIn("vless_enabled", panel)
        self.assertIn('path == "/vless/off"', backend)
        self.assertIn('path == "/vless/on"', backend)
        self.assertIn("vless_enabled = not xray_is_off()", backend)
        self.assertIn("ConditionPathExists=!/etc/hy2-aio/xray.off", config)

    def test_xray_turn_off_sets_flag_and_stops_service(self):
        actions = []
        self.namespace["request_xray"] = lambda act: actions.append(act)
        self.namespace["collect"] = lambda: {"generated_at": "2026-11-27T00:00:00Z"}

        data = self.namespace["xray_turn_off"]()
        self.assertTrue(self.off_file.exists())
        self.assertEqual(["stop"], actions)
        self.assertEqual("2026-11-27T00:00:00Z", data["generated_at"])

    def test_xray_turn_on_requires_enabled_user(self):
        self.users_file.write_text(
            json.dumps({"alice": {"password": "pw", "disabled": True}}) + "\n",
            encoding="utf-8",
        )
        self.off_file.write_text("1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "至少一个用户"):
            self.namespace["xray_turn_on"]()
        self.assertTrue(self.off_file.exists())

    def test_xray_turn_on_clears_flag_rebuilds_and_restarts(self):
        self.off_file.write_text("1\n", encoding="utf-8")
        events = []
        self.namespace["rebuild_xray_config"] = lambda: events.append("rebuild")
        self.namespace["request_xray"] = lambda act: events.append(f"xray:{act}")
        self.namespace["collect"] = lambda: {"generated_at": "2026-11-27T00:00:01Z"}

        data = self.namespace["xray_turn_on"]()
        self.assertFalse(self.off_file.exists())
        self.assertEqual(["rebuild", "xray:restart"], events)
        self.assertEqual("2026-11-27T00:00:01Z", data["generated_at"])

    def test_xray_turn_on_restores_off_flag_if_rebuild_fails(self):
        self.off_file.write_text("1\n", encoding="utf-8")

        def boom():
            raise RuntimeError("broken xray config")

        self.namespace["rebuild_xray_config"] = boom
        with self.assertRaisesRegex(RuntimeError, "broken xray config"):
            self.namespace["xray_turn_on"]()
        self.assertTrue(self.off_file.exists())

    def test_apply_xray_after_users_does_not_restart_when_vless_is_off(self):
        self.off_file.write_text("1\n", encoding="utf-8")
        actions = []
        self.namespace["request_xray"] = lambda act: actions.append(act)

        self.namespace["apply_xray_after_users"]({"alice": {"disabled": False}})
        self.assertEqual([], actions)

    def test_handler_vless_off_and_on_endpoints(self):
        self.namespace["xray_turn_off"] = lambda: {"generated_at": "2026-11-27T00:00:02Z"}
        self.namespace["xray_turn_on"] = lambda: {"generated_at": "2026-11-27T00:00:03Z"}

        class FakeRequest:
            headers = {"Content-Type": "application/json"}

            def __init__(self, path):
                self.path = path
                self.response = None

            def require_api_secret(self):
                return True

            def require_same_origin(self):
                return True

            def require_rate_limit(self, *_args):
                return True

            def send_json(self, status, payload):
                self.response = (status, payload)

        req_off = FakeRequest("/vless/off")
        self.namespace["Handler"].do_POST(req_off)
        self.assertEqual(200, req_off.response[0])
        self.assertFalse(req_off.response[1]["vless_enabled"])

        req_on = FakeRequest("/vless/on")
        self.namespace["Handler"].do_POST(req_on)
        self.assertEqual(200, req_on.response[0])
        self.assertTrue(req_on.response[1]["vless_enabled"])


if __name__ == "__main__":
    unittest.main()
