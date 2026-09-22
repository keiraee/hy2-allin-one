import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_content_type_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_ct_{os.getpid()}.sh"
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


class ApiContentTypeTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.namespace["collect"] = lambda *args, **kwargs: {"generated_at": "t"}

    class FakeRequest:
        def __init__(self, headers, path="/sync"):
            self.path = path
            self.headers = headers
            self.response = None

        def require_api_secret(self):
            return True

        def require_same_origin(self):
            return True

        def require_rate_limit(self, *_args):
            return True

        def send_json(self, status, payload):
            self.response = (status, payload)

    def post(self, headers):
        request = self.FakeRequest(headers)
        self.namespace["Handler"].do_POST(request)
        return request.response

    def test_post_without_json_content_type_is_rejected(self):
        # text/plain 简单请求是 CSRF 的载体，必须在路由前按 415 拒掉；
        # application/json 会触发 CORS 预检，浏览器自然挡住。
        for headers in ({}, {"Content-Type": "text/plain"}, {"Content-Type": "application/x-www-form-urlencoded"}):
            status, payload = self.post(headers)
            self.assertEqual(415, status, f"headers={headers} -> {payload}")

    def test_post_with_json_content_type_proceeds(self):
        status, _ = self.post({"Content-Type": "application/json"})
        self.assertEqual(200, status)

    def test_post_accepts_json_with_charset_suffix(self):
        status, _ = self.post({"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual(200, status)

    def test_cli_api_post_declares_json_content_type(self):
        result = run_bash(
            """
set -Eeuo pipefail
source lib/core.sh
API_SECRET=test-secret
curl() { printf '%s\\n' "$*"; }
api_post sync
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertIn("Content-Type: application/json", result.stdout)


if __name__ == "__main__":
    unittest.main()
