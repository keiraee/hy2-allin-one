"""Panel maintenance actions: restart cores and trigger async upgrade."""

import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    source = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
    namespace = {"__name__": "hy2_aio_maintenance_test"}
    exec(compile(source, "server.py", "exec"), namespace)
    return namespace


class PanelMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cmd_file = self.root / "hysteria-cmd"
        self.flag_file = self.root / "reload-hysteria"
        self.namespace["HYSTERIA_CMD_FILE"] = self.cmd_file
        self.namespace["HYSTERIA_RELOAD_FLAG"] = self.flag_file

    def tearDown(self):
        self.temporary.cleanup()

    def test_control_script_and_panel_wire_upgrade_and_restart(self):
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        panel = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        backend = (ROOT / "app" / "server.py").read_text(encoding="utf-8")

        self.assertIn("restart-all)", config)
        self.assertIn("upgrade)", config)
        self.assertIn("systemd-run", config)
        self.assertIn("/usr/local/bin/hy2 upgrade", config)

        self.assertIn('id="restartBtn"', panel)
        self.assertIn('id="upgradeBtn"', panel)
        self.assertIn("api/restart", panel)
        self.assertIn("api/upgrade/check", panel)
        self.assertIn("api/upgrade", panel)
        self.assertIn("up_to_date", panel)
        self.assertIn("location.reload()", panel)

        self.assertIn('path == "/restart"', backend)
        self.assertIn('path == "/upgrade/check"', backend)
        self.assertIn('path == "/upgrade"', backend)

    def test_check_upgrade_status_compares_version_and_commit_hash(self):
        sha_same = "a" * 40
        sha_new = "b" * 40

        def fake_gh(url):
            if url.endswith("/releases/latest"):
                return {"tag_name": "v2.0.0"}
            return {"sha": sha_same}

        self.namespace["_github_get_json"] = fake_gh
        same = self.namespace["check_upgrade_status"](
            {"AIO_VERSION": "v2.0.0.aaaaaaa", "HY2_REPO_SHA": sha_same}
        )
        self.assertTrue(same["up_to_date"])
        self.assertEqual("v2.0.0", same["latest"])
        self.assertEqual("aaaaaaa", same["latest_commit"])

        diff = self.namespace["check_upgrade_status"](
            {"AIO_VERSION": "v2.0.0.bbbbbbb", "HY2_REPO_SHA": sha_new}
        )
        self.assertFalse(diff["up_to_date"])

    def test_request_upgrade_writes_upgrade_cmd_and_returns(self):
        seen = []

        def clear_flag():
            for _ in range(20):
                if self.flag_file.exists():
                    seen.append(self.cmd_file.read_text(encoding="utf-8").strip())
                    self.flag_file.unlink()
                    return
                time.sleep(0.05)

        t = threading.Thread(target=clear_flag, daemon=True)
        t.start()
        self.namespace["request_upgrade"]()
        t.join(timeout=2)
        self.assertEqual(["upgrade"], seen)

    def test_request_restart_services_writes_restart_all_and_collects(self):
        seen = []
        self.namespace["collect"] = lambda run_backup=True: {
            "generated_at": "2026-11-27T00:00:00Z",
            "run_backup": run_backup,
        }

        def clear_flag():
            for _ in range(20):
                if self.flag_file.exists():
                    seen.append(self.cmd_file.read_text(encoding="utf-8").strip())
                    self.flag_file.unlink()
                    return
                time.sleep(0.05)

        t = threading.Thread(target=clear_flag, daemon=True)
        t.start()
        data = self.namespace["request_restart_services"]()
        t.join(timeout=2)
        self.assertEqual(["restart-all"], seen)
        self.assertFalse(data["run_backup"])

    def test_handler_upgrade_and_restart_endpoints(self):
        called = []
        self.namespace["request_upgrade"] = lambda: called.append("upgrade")
        self.namespace["request_restart_services"] = lambda: (
            called.append("restart") or {"generated_at": "2026-11-27T00:00:09Z"}
        )

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

        r1 = FakeRequest("/upgrade")
        self.namespace["Handler"].do_POST(r1)
        self.assertEqual(200, r1.response[0])
        self.assertTrue(r1.response[1]["started"])

        r2 = FakeRequest("/restart")
        self.namespace["Handler"].do_POST(r2)
        self.assertEqual(200, r2.response[0])
        self.assertEqual("2026-11-27T00:00:09Z", r2.response[1]["generated_at"])
        self.assertEqual(["upgrade", "restart"], called)


if __name__ == "__main__":
    unittest.main()
