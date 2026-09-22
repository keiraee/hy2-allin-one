import os
import subprocess
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
    namespace = {"__name__": "hy2_aio_on_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_on_{os.getpid()}.sh"
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


class Hy2OnCliTests(unittest.TestCase):
    def test_cli_hy2_on_restarts_hysteria_to_apply_config(self):
        # 服务已在运行时 start 不会重载，刚重建的配置不生效；必须 restart。
        result = run_bash(
            """
set -Eeuo pipefail
source lib/core.sh
source lib/user.sh
source lib/cli.sh
base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT
USERS_FILE="$base/users.json"
HYSTERIA_CONFIG="$base/config.yaml"
HY2_OFF_FILE="$base/hy2.off"
REBUILD_FILE=/bin/true
printf '%s\\n' '{"alice":{}}' > "$USERS_FILE"
touch "$HYSTERIA_CONFIG"
need_root() { :; }
read_env() { :; }
wait_hysteria_stats_api() { :; }
chown() { :; }
chmod() { :; }
systemctl() { printf 'systemctl %s\\n' "$*"; }
hy2_on_cmd
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertIn("systemctl restart hysteria-server.service", result.stdout)
        self.assertNotIn("systemctl start hysteria-server.service", result.stdout)


class Hy2OnBackendTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()
        self.requests = []
        self.ns["load_users"] = lambda: {"alice": {"disabled": False}}
        self.ns["request_hysteria"] = lambda action: self.requests.append(action)
        self.ns["collect"] = lambda **kwargs: {}

    def test_backend_hy2_turn_on_restarts_hysteria(self):
        with mock.patch.object(
            self.ns["subprocess"], "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr="")
        ):
            self.ns["hy2_turn_on"]()
        self.assertEqual(["restart"], self.requests)


if __name__ == "__main__":
    unittest.main()
