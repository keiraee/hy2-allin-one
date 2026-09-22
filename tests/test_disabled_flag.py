import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_disabled_flag_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


def load_access_source():
    text = (ROOT / "lib" / "access.sh").read_text(encoding="utf-8")
    start = text.index("<<'PY'\n") + len("<<'PY'\n")
    end = text.index("\nPY\n", start)
    return text[start:end]


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_dis_{os.getpid()}.sh"
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


ENV = {
    "DOMAIN": "panel.example.com",
    "PANEL_PORT": "443",
    "PUBLIC_IP": "203.0.113.1",
    "HY2_PORT": "8443",
    "SNI": "www.amazon.sg",
    "OBFS_ENABLED": "false",
    "TOTAL_BYTES": "1000",
}


class StubSubscriptionHandler:
    def __init__(self):
        self.command = "GET"
        self.headers = {}
        self.status = None
        self.json = None
        self.wfile = io.BytesIO()

    def require_rate_limit(self, *_args):
        return True

    def send_response(self, status, *_args):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def send_error(self, status, *_args):
        self.status = status

    def send_json(self, status, payload):
        self.status = status
        self.json = payload


class DisabledFlagNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.ns["MODE_FILE"] = root / "client-mode.json"
        self.ns["DATA_FILE"] = root / "data.json"
        self.ns["HY2_OFF_FILE"] = root / "hy2.off"
        self.ns["load_env"] = lambda: dict(ENV)

    def tearDown(self):
        self.temporary.cleanup()

    def serve_subscription(self, disabled_value):
        users = {
            "alice": {"password": "pw", "token": "tok", "disabled": disabled_value}
        }
        self.ns["load_users"] = lambda: users
        stub = StubSubscriptionHandler()
        self.ns["Handler"].send_subscription(stub, "tok")
        return stub.status

    def test_subscription_treats_string_false_as_enabled(self):
        # 三套 disabled 判断必须同归 user_is_disabled："false" 字符串是启用。
        self.assertEqual(200, self.serve_subscription("false"))

    def test_subscription_still_blocks_disabled_users(self):
        self.assertEqual(403, self.serve_subscription(True))
        self.assertEqual(403, self.serve_subscription("true"))

    def test_panel_users_payload_normalizes_disabled_flag(self):
        self.ns["DATA_FILE"].write_text('{"users": [], "server": {}, "summary": {}}', encoding="utf-8")
        self.ns["publish_users_to_panel"](
            {
                "alice": {"note": "", "disabled": "false"},
                "bob": {"note": "", "disabled": "true"},
            },
            "2026-09-22T00:00:00",
        )
        data = json.loads(self.ns["DATA_FILE"].read_text(encoding="utf-8"))
        flags = {item["username"]: item["disabled"] for item in data["users"]}
        self.assertFalse(flags["alice"], f"字符串 false 应视为启用：{flags}")
        self.assertTrue(flags["bob"], f"字符串 true 应视为禁用：{flags}")

    def test_access_file_reports_status_with_normalized_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "config.env"
            users_file = root / "users.json"
            mode_file = root / "client-mode.json"
            out_file = root / "access.txt"
            env_file.write_text(
                "\n".join(f"{key}={value}" for key, value in ENV.items())
                + "\nAIO_VERSION=1.6.1\nPANEL_PATH=p\nPANEL_USER=admin\nPANEL_PASS=secret\n",
                encoding="utf-8",
            )
            users_file.write_text(
                json.dumps(
                    {
                        "alice": {"password": "pw", "token": "tok", "disabled": "false"},
                        "bob": {"password": "pw2", "token": "tok2", "disabled": "true"},
                    }
                ),
                encoding="utf-8",
            )
            mode_file.write_text("{}", encoding="utf-8")
            source = load_access_source()
            argv = sys.argv
            sys.argv = ["access", str(env_file), str(users_file), str(mode_file), str(out_file)]
            try:
                exec(compile(source, "access.py", "exec"), {"__name__": "access_test"})
            finally:
                sys.argv = argv
            text = out_file.read_text(encoding="utf-8")
            self.assertIn("状态：正常", text)
            self.assertIn("状态：已禁用", text)
            alice_block = text.split("【alice】", 1)[1].split("【bob】", 1)[0]
            self.assertIn("状态：正常", alice_block)

    def test_menu_toggle_uses_normalized_flag(self):
        result = run_bash(
            """
set -Eeuo pipefail
source lib/core.sh
source lib/user.sh
source lib/cli.sh
base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT
USERS_FILE="$base/users.json"
printf '%s\\n' '{"alice":{"disabled":"false"},"bob":{"disabled":"true"}}' > "$USERS_FILE"
modify_user() { printf 'modify %s\\n' "$*"; }
printf 'alice\\n' | menu_toggle_user
printf 'bob\\n' | menu_toggle_user
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertIn("modify disable alice", result.stdout)
        self.assertIn("modify enable bob", result.stdout)


if __name__ == "__main__":
    unittest.main()
