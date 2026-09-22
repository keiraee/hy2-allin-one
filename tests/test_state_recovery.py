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
    namespace = {"__name__": "hy2_aio_state_recovery_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


BLANK = {"month": "1970-01", "network": {}, "users": {}, "last_history": 0}


class LoadStateTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary.name) / "state.json"
        self.ns["STATE_FILE"] = self.state_file
        self.ns["blank_state"] = lambda iface: dict(BLANK)

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_state_returns_blank_without_error(self):
        state, error = self.ns["load_state"]("eth0")
        self.assertEqual(BLANK, state)
        self.assertEqual("", error)

    def test_corrupt_state_is_preserved_and_reported(self):
        # 损坏时绝不能静默清零：保留副本供手工恢复，并把事故报到面板错误条。
        self.state_file.write_text("{not json", encoding="utf-8")
        state, error = self.ns["load_state"]("eth0")
        self.assertEqual(BLANK, state)
        self.assertIn("state.json", error)
        backup = self.state_file.with_name("state.json.corrupt")
        self.assertTrue(backup.is_file(), "损坏副本未保留")
        self.assertEqual("{not json", backup.read_text(encoding="utf-8"))

    def test_invalid_structure_treated_as_corrupt(self):
        self.state_file.write_text('["not", "a", "dict"]', encoding="utf-8")
        state, error = self.ns["load_state"]("eth0")
        self.assertEqual(BLANK, state)
        self.assertIn("state.json", error)
        self.assertTrue(self.state_file.with_name("state.json.corrupt").is_file())

    def test_valid_state_passes_through(self):
        self.state_file.write_text('{"users": {"alice": {}}}', encoding="utf-8")
        state, error = self.ns["load_state"]("eth0")
        self.assertEqual({"users": {"alice": {}}}, state)
        self.assertEqual("", error)
        self.assertFalse(self.state_file.with_name("state.json.corrupt").exists())

    def test_forget_user_preserves_corrupt_state_before_overwrite(self):
        self.state_file.write_text("{bad", encoding="utf-8")
        self.ns["MODE_FILE"] = Path(self.temporary.name) / "client-mode.json"
        self.ns["forget_user_side_state"]("bob")
        backup = self.state_file.with_name("state.json.corrupt")
        self.assertTrue(backup.is_file(), "删用户覆盖前未保留损坏副本")
        self.assertEqual("{bad", backup.read_text(encoding="utf-8"))


class StaleUserStateGcTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()

    def test_drop_stale_user_state_removes_all_buckets(self):
        # 删用户清理与周期采集存在读改写竞态，残留可能被写“复活”；
        # 采集统一回收不在 users.json 的用户残留，竞态最长存活一个采集周期。
        state = {
            "users": {"bob": {"month_tx": 1}, "alice": {"month_tx": 2}},
            "destinations": {"bob": {"b.example": {}}, "alice": {"a.example": {}}},
            "client_ips": {"bob": {"198.51.100.7": {}}, "alice": {"203.0.113.9": {}}},
            "stream_bytes": {"bob:1:2": {"tx": 1}, "alice:3:4": {"tx": 2}},
        }
        self.ns["drop_stale_user_state"](state, {"alice": {}})
        self.assertNotIn("bob", state["users"])
        self.assertNotIn("bob", state["destinations"])
        self.assertNotIn("bob", state["client_ips"])
        self.assertNotIn("bob:1:2", state["stream_bytes"])
        self.assertIn("alice", state["users"])
        self.assertIn("alice", state["destinations"])
        self.assertIn("alice", state["client_ips"])
        self.assertIn("alice:3:4", state["stream_bytes"])

    def test_collect_calls_the_gc(self):
        source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn("drop_stale_user_state(state, users)", source)


if __name__ == "__main__":
    unittest.main()
