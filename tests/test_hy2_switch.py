import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_switch_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class Hy2SwitchSourceTests(unittest.TestCase):
    def test_rebuild_has_no_placeholder_account(self):
        source = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        self.assertNotIn(".hy2-disabled", source)
        self.assertIn("userpass: {}", source)
        self.assertIn("ConditionPathExists=!", source)
        self.assertIn("hysteria-cmd", source)

    def test_cli_and_panel_expose_the_switch(self):
        cli = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        panel = (ROOT / "lib" / "panel.sh").read_text(encoding="utf-8")
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        usage = (ROOT / "bin" / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn("hy2_on_cmd()", cli)
        self.assertIn("hy2_off_cmd()", cli)
        self.assertIn('id="hy2OffBanner"', panel)
        self.assertIn("api/hy2/on", panel)
        self.assertIn("api/hy2/off", panel)
        self.assertIn('status==="off"', panel)
        self.assertIn('path == "/hy2/on"', backend)
        self.assertIn("请先启用至少一个用户", backend)
        self.assertIn("hy2 on", usage)
        self.assertIn("hy2 off", usage)

    def test_uninstall_removes_the_switch_drop_in(self):
        source = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        self.assertIn("HYSTERIA_DROPIN_DIR", source)
        backup = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8")
        self.assertIn("HYSTERIA_DROPIN_DIR", backup)


class Hy2SwitchBackendTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.off_file = self.root / "hy2.off"
        self.users_file = self.root / "users.json"
        self.rebuild_file = self.root / "rebuild_config.py"
        self.users_file.write_text(
            json.dumps({"alice": {"password": "x", "disabled": True}}) + "\n",
            encoding="utf-8",
        )
        self.rebuild_file.write_text("# fixture\n", encoding="utf-8")
        self.namespace.update(
            {
                "HY2_OFF_FILE": self.off_file,
                "USERS_FILE": self.users_file,
                "REBUILD_FILE": self.rebuild_file,
            }
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_has_enabled_users_matches_disabled_flag(self):
        self.assertFalse(self.namespace["has_enabled_users"]({"a": {"disabled": True}}))
        self.assertTrue(self.namespace["has_enabled_users"]({"a": {"disabled": False}}))
        self.assertTrue(
            self.namespace["has_enabled_users"](
                {"a": {"disabled": True}, "b": {"disabled": False}}
            )
        )

    def test_turn_on_requires_an_enabled_user(self):
        with self.assertRaisesRegex(ValueError, "请先启用至少一个用户"):
            self.namespace["hy2_turn_on"]()
        self.assertFalse(self.off_file.exists())

    def test_turn_on_starts_after_rebuild(self):
        self.users_file.write_text(
            json.dumps({"alice": {"password": "x", "disabled": False}}) + "\n",
            encoding="utf-8",
        )
        self.off_file.write_text("1\n", encoding="utf-8")
        self.namespace["subprocess"] = SimpleNamespace(
            run=mock.Mock(
                return_value=SimpleNamespace(returncode=0, stderr="")
            ),
            DEVNULL=mock.Mock(),
        )
        self.namespace["request_hysteria"] = mock.Mock()
        self.namespace["collect"] = lambda: {"generated_at": "now"}

        data = self.namespace["hy2_turn_on"]()

        self.assertFalse(self.off_file.exists())
        self.namespace["request_hysteria"].assert_called_once_with("start")
        self.assertEqual("now", data["generated_at"])

    def test_collect_skips_hysteria_api_when_off(self):
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn("hy2_enabled = not hy2_is_off()", backend)
        self.assertIn('hysteria_api("/traffic"', backend)
        self.assertIn('"off" if not hy2_enabled', backend)


if __name__ == "__main__":
    unittest.main()
