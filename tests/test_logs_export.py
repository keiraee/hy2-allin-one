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
    namespace = {"__name__": "hy2_aio_logs_export_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class LogsExportTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()

    def test_default_window_matches_menu_18_units_and_keeps_newest(self):
        args = self.namespace["journalctl_export_args"]()
        self.assertEqual(args[0], "journalctl")
        self.assertIn("hysteria-server.service", args)
        self.assertIn("hy2-aio.service", args)
        self.assertIn("caddy.service", args)
        self.assertIn("--no-pager", args)
        self.assertEqual(args[args.index("--since") + 1], "24 hours ago")
        self.assertEqual(args[args.index("-n") + 1], "10000")

    def test_range_presets_and_invalid_range(self):
        self.assertEqual(
            self.namespace["journalctl_export_args"]("1h")[
                self.namespace["journalctl_export_args"]("1h").index("--since") + 1
            ],
            "1 hour ago",
        )
        self.assertEqual(
            self.namespace["journalctl_export_args"]("3d")[
                self.namespace["journalctl_export_args"]("3d").index("--since") + 1
            ],
            "3 days ago",
        )
        with self.assertRaisesRegex(ValueError, "范围"):
            self.namespace["journalctl_export_args"]("7d")

    def test_export_runs_journalctl_with_timeout(self):
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stdout="line\n", stderr="")

        with mock.patch.object(self.namespace["subprocess"], "run", fake_run):
            body, filename = self.namespace["export_service_logs"]("24h")
        self.assertEqual(body, b"line\n")
        self.assertRegex(filename, r"^hy2-logs-\d{8}-\d{4}\.txt$")
        self.assertEqual(captured["kwargs"].get("timeout"), 15)
        self.assertEqual(captured["args"][captured["args"].index("-n") + 1], "10000")

    def test_panel_and_api_and_journal_group(self):
        panel = (ROOT / "lib" / "panel.sh").read_text(encoding="utf-8")
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        self.assertIn("api/logs/export", panel)
        self.assertIn("导出日志", panel)
        self.assertIn('path == "/logs/export"', backend)
        self.assertIn("systemd-journal", config)
        self.assertIn("SupplementaryGroups=hysteria caddy systemd-journal", config)


if __name__ == "__main__":
    unittest.main()
