import os
import subprocess
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
