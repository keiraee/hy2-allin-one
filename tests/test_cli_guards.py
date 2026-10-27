import collections
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_gd_{os.getpid()}.sh"
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


ROLLBACK_PRELUDE = """
set -Eeuo pipefail
source lib/core.sh
source lib/backup.sh
need_root() { :; }
read_env() { :; }
ensure_rollback_dir() { :; }
"""


class RollbackGuardTests(unittest.TestCase):
    def test_rollback_refuses_non_interactive_without_yes(self):
        # 脚本里非交互跑 hy2 rollback 不能静默“取消成功”——那会让调用方误以为已回滚。
        result = run_bash(ROLLBACK_PRELUDE + 'rollback_cmd < /dev/null\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("交互", result.stderr)

    def test_rollback_hy2_yes_bypasses_prompt(self):
        result = run_bash(
            ROLLBACK_PRELUDE + 'HY2_YES=1 rollback_cmd < /dev/null || true\ntest ! -f "$TMPDIR/hy2-nope"\n'
        )
        # 过了交互护栏后应继续走查找快照流程（此处无快照而失败），stderr 不含“交互”。
        self.assertNotIn("交互", result.stderr)


class MenuNumberingTests(unittest.TestCase):
    def test_each_menu_number_maps_to_exactly_one_action(self):
        """菜单是 case 分派；两处同号时 bash 静默取靠前的那个，后一个功能点了没反应。"""
        text = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        body = text[text.index("menu_interactive() {"):]
        body = body[: body.index("\n  done\n}")]
        numbers = re.findall(r"^\s{6}(\d+)\)", body, re.MULTILINE)
        duplicated = [n for n, count in collections.Counter(numbers).items() if count > 1]
        self.assertEqual([], duplicated, f"菜单项编号冲突：{duplicated}")
        listed = re.findall(r'^\s{2}(\d+)\)', text[text.index("show_menu() {"):text.index("menu_interactive() {")], re.MULTILINE)
        self.assertEqual([], [n for n in listed if n not in numbers], f"菜单列出但无分派：{listed}")


class StatusAdblockTests(unittest.TestCase):
    """hy2 status 的去广告行必须反映面板写下的覆盖（adblock.json），不能只看 config.env。"""

    def render_status(self, adblock_json: str) -> str:
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            env_file = root / "config.env"
            env_file.write_text(
                "DOMAIN=panel.example.com\nPANEL_PORT=443\nPANEL_PATH=p\n"
                "HY2_PORT=8443\nSTATS_PORT=9999\n"
                # BACKEND_HOST/BACKEND_PORT 是 core.sh 的 readonly 常量，不能进 config.env
                "ADBLOCK_ENABLED=true\nADBLOCK_LEVEL=lite\n",
                encoding="utf-8",
            )
            adblock_file = root / "adblock.json"
            adblock_file.write_text(adblock_json, encoding="utf-8")
            env_rel = env_file.relative_to(ROOT).as_posix()
            adblock_rel = adblock_file.relative_to(ROOT).as_posix()
            result = run_bash(
                "set -Eeuo pipefail\n"
                "source lib/core.sh\n"
                "source lib/config.sh\n"
                "source lib/cli.sh\n"
                "need_root() { :; }\n"
                f'ENV_FILE="{env_rel}"\n'
                f'ADBLOCK_FILE="{adblock_rel}"\n'
                "systemctl() { :; }\n"
                "ss() { :; }\n"
                "status_cmd\n"
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            return result.stdout

    def adblock_line(self, adblock_json: str) -> str:
        return next(
            line for line in self.render_status(adblock_json).splitlines()
            if line.startswith("去广告：")
        )

    def test_panel_override_turns_status_off(self):
        self.assertEqual("去广告：off", self.adblock_line('{"enabled": false}'))

    def test_status_follows_config_env_without_override(self):
        self.assertEqual("去广告：on (lite)", self.adblock_line("{}"))

    def test_status_shows_effective_level(self):
        self.assertEqual("去广告：on (full)", self.adblock_line('{"level": "full"}'))


class LogsGuardTests(unittest.TestCase):
    def test_logs_rejects_non_numeric_lines(self):
        result = run_bash(
            """
set -Eeuo pipefail
source lib/core.sh
source lib/cli.sh
need_root() { :; }
journalctl() { printf 'journalctl called\\n'; }
logs_cmd abc
"""
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("行数", result.stderr)


if __name__ == "__main__":
    unittest.main()
