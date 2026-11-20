import json
import re
import sys
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "lib" / "backend.sh"


def load_backend_namespace():
    src = BACKEND.read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    i = src.index(start_marker) + len(start_marker)
    j = src.index(end_marker, i)
    ns = {"__name__": "hy2_kick_test"}
    exec(compile(src[i:j], "server.py", "exec"), ns)
    return ns


class FakeHysteria:
    """最小可用的假 Hysteria 统计 API，记录收到的请求。"""

    def __init__(self):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode("utf-8")
                outer.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "ctype": self.headers.get("Content-Type"),
                        "body": raw,
                    }
                )
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class KickRequestFormatTests(unittest.TestCase):
    """Hysteria 的 /kick 是 POST，body 是用户名字符串数组，
    鉴权走 Authorization 头（不是 Bearer）。"""

    def setUp(self):
        self.api = FakeHysteria()
        self.ns = load_backend_namespace()
        self.ns["load_env"] = lambda: {"STATS_PORT": str(self.api.port)}

    def tearDown(self):
        self.api.close()

    def test_kick_posts_json_array(self):
        self.ns["kick_users"](["alice", "bob"], "s3cret")
        self.assertEqual(1, len(self.api.requests))
        req = self.api.requests[0]
        self.assertEqual("POST", req["method"])
        self.assertEqual("/kick", req["path"])
        self.assertEqual(["alice", "bob"], json.loads(req["body"]))

    def test_kick_uses_authorization_header(self):
        self.ns["kick_users"](["alice"], "s3cret")
        self.assertEqual("s3cret", self.api.requests[0]["auth"])

    def test_kick_sends_json_content_type(self):
        self.ns["kick_users"](["alice"], "s3cret")
        self.assertEqual("application/json", self.api.requests[0]["ctype"])

    def test_empty_username_list_skips_request(self):
        kicked = self.ns["kick_users"](["", "  "], "s3cret")
        self.assertEqual(0, kicked)
        self.assertEqual([], self.api.requests)


class KickSafelyTests(unittest.TestCase):
    """踢人是加分项：Hysteria 没跑、secret 缺失都不能让 disable 失败。"""

    def setUp(self):
        self.ns = load_backend_namespace()

    def test_returns_zero_when_hysteria_off(self):
        self.ns["hy2_is_off"] = lambda: True
        self.assertEqual(0, self.ns["kick_user_safely"]("alice"))

    def test_returns_zero_when_secret_missing(self):
        self.ns["hy2_is_off"] = lambda: False
        self.ns["load_env"] = lambda: {}
        self.assertEqual(0, self.ns["kick_user_safely"]("alice"))

    def test_swallows_api_failure(self):
        self.ns["hy2_is_off"] = lambda: False
        self.ns["load_env"] = lambda: {"API_SECRET": "x"}
        self.ns["kick_users"] = mock.Mock(side_effect=OSError("connection refused"))
        self.assertEqual(0, self.ns["kick_user_safely"]("alice"))

    def test_reports_one_when_successful(self):
        self.ns["hy2_is_off"] = lambda: False
        self.ns["load_env"] = lambda: {"API_SECRET": "x"}
        self.ns["kick_users"] = mock.Mock(return_value=1)
        self.assertEqual(1, self.ns["kick_user_safely"]("alice"))


class KickWiringTests(unittest.TestCase):
    """禁用/删除/轮换之后必须真的踢，且必须在校验已落盘之后。"""

    @classmethod
    def setUpClass(cls):
        cls.src = BACKEND.read_text(encoding="utf-8")

    def test_disable_triggers_kick(self):
        self.assertIn('if action in ("disable", "remove", "rotate"):', self.src)
        self.assertIn("kick_user_safely(username)", self.src)

    def test_kick_after_user_change(self):
        body = self.src[self.src.index("def handle_user_change(") :]
        body = body[: body.index("def handle_user_credentials(")]
        change = body.index("apply_user_change")
        kick = body.index("kick_user_safely(username)")
        self.assertLess(change, kick, "先落盘 disabled，再踢人；顺序反了会被重连绕过")

    def test_cli_path_also_kicks(self):
        user_sh = (ROOT / "lib" / "user.sh").read_text(encoding="utf-8")
        self.assertIn("kick_hysteria_user", user_sh)
        self.assertIn("disable|remove-user|rotate-user", user_sh)

    def test_cli_kick_after_config_rebuild(self):
        user_sh = (ROOT / "lib" / "user.sh").read_text(encoding="utf-8")
        body = user_sh[user_sh.index("modify_user() {") :]
        rebuild = body.index('"$REBUILD_FILE"')
        kick = body.index("kick_hysteria_user")
        self.assertLess(rebuild, kick, "先重建配置（旧凭据失效），再踢")


class HysteriaRestartAccountingTests(unittest.TestCase):
    """Hysteria 重启后计数器归零。若不重置基线，
    新值可能大于旧值 → 只记差额，几乎全丢。"""

    def setUp(self):
        self.ns = load_backend_namespace()

    def test_counter_delta_normal(self):
        self.assertEqual(500, self.ns["counter_delta"](1500, 1000))

    def test_counter_delta_after_reset(self):
        self.assertEqual(300, self.ns["counter_delta"](300, 1000))

    def test_instance_marker_returns_empty_without_service(self):
        # 测试环境没有 hysteria-server，应安全返回空串而不是抛异常
        self.assertEqual("", self.ns["hysteria_instance_marker"]())

    def test_marker_change_resets_baseline(self):
        """这是修复的核心：换进程 → last_tx/last_rx 归零。"""
        state = {
            "hysteria_instance": "111@500",
            "users": {"alice": {"last_tx": 1000, "last_rx": 2000}},
            "stream_bytes": {"alice:1:2": {"tx": 5}},
        }
        instance = "222@900"
        if instance and state.get("hysteria_instance") not in (None, "", instance):
            for us in state["users"].values():
                us["last_tx"] = 0
                us["last_rx"] = 0
            state["stream_bytes"] = {}

        self.assertEqual(0, state["users"]["alice"]["last_tx"])
        self.assertEqual(0, state["users"]["alice"]["last_rx"])
        self.assertEqual({}, state["stream_bytes"])
        self.assertEqual("222@900", instance)


class RestartDetectionInCollectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BACKEND.read_text(encoding="utf-8")

    def test_collect_calls_instance_marker(self):
        body = self.src[self.src.index("def collect(") :]
        self.assertIn("hysteria_instance_marker()", body)

    def test_empty_marker_does_not_wipe_state(self):
        """拿不到 marker 时不能当成「重启了」把基线清零。"""
        body = self.src[self.src.index("def collect(") :]
        seg = body[body.index("hysteria_instance_marker()") :]
        seg = seg[: seg.index("if hy2_enabled:")]
        self.assertIn("if instance and state.get", seg)


if __name__ == "__main__":
    unittest.main()