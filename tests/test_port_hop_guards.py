import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    path = ROOT / "tests" / f".tmp_hop_{os.getpid()}.sh"
    path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
    try:
        return subprocess.run(
            ["bash", path.relative_to(ROOT).as_posix()],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)


PRELUDE = """
set -Eeuo pipefail
source lib/core.sh
need_root() { :; }
"""


class HopRangeGuardTests(unittest.TestCase):
    def test_default_range_is_base_plus_1000(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; default_hop_range\n')
        self.assertEqual("8443-9443", result.stdout.strip())

    def test_default_range_caps_at_65535(self):
        result = run_bash(PRELUDE + 'HY2_PORT=65000; default_hop_range\n')
        self.assertEqual("65000-65535", result.stdout.strip())

    def test_hop_range_falls_back_to_default(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; PORT_HOP_RANGE=""; hop_range\n')
        self.assertEqual("8443-9443", result.stdout.strip())

    def test_range_must_start_at_hy2_port(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; validate_hop_range 500-600\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("必须从代理端口", result.stderr)

    def test_range_span_limit(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; validate_hop_range 8443-10444\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("跨度", result.stderr)

    def test_range_accepts_boundaries(self):
        result = run_bash(
            PRELUDE + "HY2_PORT=8443; validate_hop_range 8443-10443\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_range_rejects_malformed(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; validate_hop_range 8443:9443\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("格式", result.stderr)


class HopRedirectRangeTests(unittest.TestCase):
    def test_redirect_starts_after_base_port(self):
        result = run_bash(
            PRELUDE
            + 'HY2_PORT=8443; PORT_HOP_RANGE=8443-9443; hop_redirect_range\n'
        )
        self.assertEqual("8444-9443", result.stdout.strip())

    def test_redirect_rejects_bad_range(self):
        result = run_bash(
            PRELUDE
            + "HY2_PORT=8443; PORT_HOP_RANGE=500-600; hop_redirect_range\n"
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout.strip())


class HopIntervalGuardTests(unittest.TestCase):
    def test_interval_accepts_bounds(self):
        for value in ("5", "3600"):
            result = run_bash(PRELUDE + f"validate_hop_interval {value}\n")
            self.assertEqual(0, result.returncode, result.stderr)

    def test_interval_rejects_below_5(self):
        result = run_bash(PRELUDE + "validate_hop_interval 4\n")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("5-3600", result.stderr)

    def test_interval_rejects_above_3600(self):
        result = run_bash(PRELUDE + "validate_hop_interval 3601\n")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("5-3600", result.stderr)


class HopSwitchTests(unittest.TestCase):
    def test_disabled_by_default(self):
        result = run_bash(PRELUDE + "PORT_HOP_ENABLED=; port_hop_enabled || echo no\n")
        self.assertEqual("no", result.stdout.strip())

    def test_truthy_values(self):
        for value in ("1", "true", "YES", "on"):
            result = run_bash(
                PRELUDE + f"PORT_HOP_ENABLED={value}; port_hop_enabled && echo yes\n"
            )
            self.assertEqual("yes", result.stdout.strip(), value)

    def test_unknown_value_is_off(self):
        result = run_bash(
            PRELUDE + "PORT_HOP_ENABLED=maybe; port_hop_enabled || echo no\n"
        )
        self.assertEqual("no", result.stdout.strip())


class HopCliEntryTests(unittest.TestCase):
    def test_installed_cli_dispatches_hop(self):
        text = (ROOT / "bin" / "hy2.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*hop\)\s+hop_cmd\s")
        self.assertIn("hy2 hop on|off", text)


if __name__ == "__main__":
    unittest.main()