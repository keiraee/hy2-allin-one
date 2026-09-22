import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str, stdin: str = ""):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_tp_{os.getpid()}.sh"
    path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
    try:
        return subprocess.run(
            ["bash", path.relative_to(ROOT).as_posix()],
            cwd=ROOT,
            input=stdin,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)


def load_access_source():
    text = (ROOT / "lib" / "access.sh").read_text(encoding="utf-8")
    start = text.index("<<'PY'\n") + len("<<'PY'\n")
    end = text.index("\nPY\n", start)
    return text[start:end]


class TrafficPlanTests(unittest.TestCase):
    def plan(self, assignments: str) -> str:
        result = run_bash(
            "set -Eeuo pipefail\nsource lib/core.sh\n"
            + assignments
            + "\nprompt_traffic_plan\nprintf '%s\\n' \"$TOTAL_BYTES\"\n"
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return result.stdout.strip()

    def test_unit_conversions(self):
        self.assertEqual("500000000", self.plan("HY2_TOTAL_UNIT=mb; HY2_TOTAL_VALUE=500"))
        self.assertEqual("2000000000", self.plan("HY2_TOTAL_UNIT=gb; HY2_TOTAL_VALUE=2"))
        self.assertEqual("1000000000000", self.plan("HY2_TOTAL_UNIT=tb; HY2_TOTAL_VALUE=1"))
        self.assertEqual("1500000000", self.plan('HY2_TOTAL_UNIT="GB"; HY2_TOTAL_VALUE=1.5'))

    def test_unlimited_flows_as_zero_bytes(self):
        self.assertEqual("0", self.plan("HY2_TOTAL_UNIT=unlimited"))
        self.assertEqual("0", self.plan("HY2_TOTAL_BYTES=0"))

    def test_explicit_bytes_and_legacy_tb_still_win(self):
        self.assertEqual("123456", self.plan("HY2_TOTAL_BYTES=123456"))
        self.assertEqual("2000000000000", self.plan("HY2_TOTAL_TB=2"))

    def test_noninteractive_defaults_to_one_tb(self):
        self.assertEqual("1000000000000", self.plan("HY2_NONINTERACTIVE=1"))

    def test_invalid_value_fails(self):
        result = run_bash(
            "set -Eeuo pipefail\nsource lib/core.sh\n"
            "HY2_TOTAL_UNIT=mb HY2_TOTAL_VALUE=abc prompt_traffic_plan\n"
        )
        self.assertNotEqual(0, result.returncode)

    def test_menu_choice_mapping(self):
        result = run_bash(
            "set -Eeuo pipefail\nsource lib/core.sh\n"
            "u() { traffic_unit_from_choice \"$1\"; echo; }\n"
            "u 1; u 2; u 3; u 4; u ''\n"
            "traffic_unit_from_choice 9 || printf 'REJECT\\n'\n"
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(["mb", "gb", "tb", "unlimited", "tb"], lines[:5])
        self.assertIn("REJECT", result.stdout)

    def test_validate_total_bytes_accepts_zero_only_as_whole_number(self):
        ok = run_bash(
            "set -Eeuo pipefail\nsource lib/core.sh\n"
            "validate_total_bytes 0\nvalidate_total_bytes 1048576\n"
        )
        self.assertEqual(0, ok.returncode, ok.stderr or ok.stdout)
        for bad in ("-1", "abc", "1.5", ""):
            result = run_bash(
                "set -Eeuo pipefail\nsource lib/core.sh\n"
                f'validate_total_bytes "{bad}"\n'
            )
            self.assertNotEqual(0, result.returncode, f"接受非法字节数：{bad!r}")

    def test_label_reflects_unit_and_unlimited(self):
        result = run_bash(
            "set -Eeuo pipefail\nsource lib/core.sh\n"
            "HY2_TOTAL_UNIT=gb; HY2_TOTAL_VALUE=1.5\nprompt_traffic_plan\n"
            'printf \'%s\\n\' "$TRAFFIC_PLAN_LABEL"\n'
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual("1.5 GB", result.stdout.splitlines()[-1])


class AccessUnlimitedDisplayTests(unittest.TestCase):
    def render_access(self, total_bytes: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "config.env"
            users_file = root / "users.json"
            mode_file = root / "client-mode.json"
            out_file = root / "access.txt"
            env_file.write_text(
                "DOMAIN=panel.example.com\nPANEL_PORT=443\nPUBLIC_IP=203.0.113.1\n"
                "HY2_PORT=8443\nSNI=www.amazon.sg\nOBFS_ENABLED=false\n"
                f"TOTAL_BYTES={total_bytes}\nAIO_VERSION=9.9.9\n"
                "PANEL_PATH=p\nPANEL_USER=admin\nPANEL_PASS=secret\n",
                encoding="utf-8",
            )
            users_file.write_text(
                '{"alice": {"password": "pw", "token": "tok", "disabled": false}}',
                encoding="utf-8",
            )
            mode_file.write_text("{}", encoding="utf-8")
            argv = sys.argv
            sys.argv = ["access", str(env_file), str(users_file), str(mode_file), str(out_file)]
            try:
                exec(compile(load_access_source(), "access.py", "exec"), {"__name__": "access_test"})
            finally:
                sys.argv = argv
            return out_file.read_text(encoding="utf-8")

    def test_zero_total_shows_unlimited(self):
        text = self.render_access("0")
        self.assertIn("无限流量", text)

    def test_nonzero_total_keeps_byte_count(self):
        text = self.render_access("1099511627776")
        self.assertIn("1099511627776", text)
        self.assertNotIn("无限流量", text)


class PanelUnlimitedDisplayTests(unittest.TestCase):
    def test_panel_renders_unlimited_quota(self):
        panel = (ROOT / "lib" / "panel.sh").read_text(encoding="utf-8")
        self.assertIn("/ 无限", panel)


if __name__ == "__main__":
    unittest.main()
