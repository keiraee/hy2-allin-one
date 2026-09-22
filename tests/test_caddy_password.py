import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_cp_{os.getpid()}.sh"
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


WRITE_CADDY_SCRIPT = """
set -Eeuo pipefail
source lib/core.sh
source lib/config.sh
source lib/install.sh
base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT
CADDY_FILE="$base/Caddyfile"
CADDY_SITE_FILE="$base/hy2-aio.caddy"
WEB_DIR="$base/web"
DOMAIN="panel.example.com"
PANEL_PORT="443"
PANEL_PATH="hy2-testpath"
PANEL_USER="admin"
PANEL_PASS="super-secret-pass"
API_SECRET="api-secret-value"
mkdir -p "$WEB_DIR" "$base/bin"
export HY2_CALL_LOG="$base/calls.log"
cat > "$base/bin/caddy" <<'EOS'
#!/bin/sh
printf '%s\\n' "caddy $*" >> "$HY2_CALL_LOG"
case "$1" in
  version) printf 'v2.11.4\\n' ;;
  hash-password) cat > /dev/null; printf 'hashed-stub\\n' ;;
esac
exit 0
EOS
chmod +x "$base/bin/caddy"
export PATH="$base/bin:$PATH"
install() { :; }
touch() { :; }
chown() { :; }
chmod() { :; }
env() { printf '%s\\n' "env $*" >> "$HY2_CALL_LOG"; /usr/bin/env "$@"; }
write_caddy
cat "$HY2_CALL_LOG"
printf '%s\\n' '--- site ---'
cat "$CADDY_SITE_FILE"
"""


class CaddyPasswordExposureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_bash(WRITE_CADDY_SCRIPT)

    def test_write_caddy_succeeds(self):
        self.assertEqual(0, self.result.returncode, self.result.stderr or self.result.stdout)
        self.assertIn("--- site ---", self.result.stdout)

    def test_password_never_appears_in_process_arguments(self):
        # argv 全员可见；密码只能走 environ（属主可读）或 stdin。
        calls = self.result.stdout.split("--- site ---", 1)[0]
        self.assertNotIn("super-secret-pass", calls)
        self.assertNotIn("--plaintext", calls)

    def test_hash_password_reads_plaintext_from_stdin(self):
        calls = self.result.stdout.split("--- site ---", 1)[0]
        self.assertIn("caddy hash-password", calls)


if __name__ == "__main__":
    unittest.main()
