import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_forget_{os.getpid()}.sh"
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


FORGET_SCRIPT = """
set -Eeuo pipefail
source lib/core.sh
source lib/user.sh
base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT
MODE_FILE="$base/client-mode.json"
STATE_DIR="$base/state"
mkdir -p "$STATE_DIR"
printf '%s\\n' '{"default":{"mode":"bbr"},"users":{"bob":{}}}' > "$MODE_FILE"
printf '%s\\n' '{"users":{"bob":{"month_tx":1},"alice":{"month_tx":2}}}' > "$STATE_DIR/state.json"
CALL_LOG="$base/calls.log"
chown() { printf 'chown %s\\n' "$*" >> "$CALL_LOG"; }
chmod() { printf 'chmod %s\\n' "$*" >> "$CALL_LOG"; }
forget_deleted_user_files bob
printf '%s\\n' '--- calls ---'
cat "$CALL_LOG"
printf '%s\\n' '--- state ---'
cat "$STATE_DIR/state.json"
"""


class ForgetUserFilesPermissionTests(unittest.TestCase):
    def run_forget(self):
        result = run_bash(FORGET_SCRIPT)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return result.stdout

    def test_state_json_gets_chown_and_chmod_like_mode_file(self):
        # CLI 以 root 重写 state.json 后若不纠权限，文件会变成 root 0600，
        # 后端（hy2-aio）读不到 → 全员月流量/历史累计被当成空状态清零。
        out = self.run_forget()
        calls = out.split("--- calls ---", 1)[1].split("--- state ---", 1)[0]
        chown_lines = [line for line in calls.splitlines() if line.startswith("chown ")]
        chmod_lines = [line for line in calls.splitlines() if line.startswith("chmod ")]
        self.assertTrue(
            any("state.json" in line for line in chown_lines),
            f"chown 未覆盖 state.json：{chown_lines}",
        )
        self.assertTrue(
            any("state.json" in line for line in chmod_lines),
            f"chmod 未覆盖 state.json：{chmod_lines}",
        )


if __name__ == "__main__":
    unittest.main()
