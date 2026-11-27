import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def rebuild_script() -> str:
    return (ROOT / "app" / "rebuild_config.py").read_text(encoding="utf-8")


class RebuildConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env_file = self.root / "config.env"
        self.users_file = self.root / "users.json"
        self.out_file = self.root / "config.yaml"
        self.out_file.write_text("listen: \":443\"\n", encoding="utf-8")
        self.env_file.write_text(
            "\n".join(
                [
                    "HY2_PORT=443",
                    "SNI_GUARD=disable",
                    "OBFS_ENABLED=false",
                    "OBFS_PASSWORD=secret",
                    "API_SECRET=token",
                    "STATS_PORT=9999",
                    "QUIC_MAX_IDLE_TIMEOUT=120s",
                    "QUIC_KEEP_ALIVE_PERIOD=5s",
                    "SPEED_TEST=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.script = self.root / "rebuild_config.py"
        self.script.write_text(rebuild_script(), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def run_rebuild(self) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HY2_ENV_FILE"] = str(self.env_file)
        env["HY2_USERS_FILE"] = str(self.users_file)
        env["HY2_HYSTERIA_CONFIG"] = str(self.out_file)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(self.script)],
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_writes_enabled_users_and_skips_disabled(self):
        self.users_file.write_text(
            '{"alice":{"password":"a1","disabled":false},'
            '"bob":{"password":"b1","disabled":true}}',
            encoding="utf-8",
        )
        result = self.run_rebuild()
        self.assertEqual(0, result.returncode, result.stderr)
        text = self.out_file.read_text(encoding="utf-8")
        self.assertIn('"alice": "a1"', text)
        self.assertNotIn("bob", text)

    def test_all_disabled_writes_empty_userpass_without_placeholder(self):
        self.users_file.write_text(
            '{"alice":{"password":"a1","disabled":true},'
            '"bob":{"password":"b1","disabled":true}}',
            encoding="utf-8",
        )
        result = self.run_rebuild()
        self.assertEqual(0, result.returncode, result.stderr)
        text = self.out_file.read_text(encoding="utf-8")
        self.assertIn("userpass: {}", text)
        self.assertNotIn(".hy2-disabled", text)
        self.assertNotIn("alice", text)
        self.assertNotIn("a1", text)
        self.assertIn("所有用户已禁用", result.stderr)

    def test_enabled_users_do_not_get_placeholder(self):
        self.users_file.write_text(
            '{"alice":{"password":"a1","disabled":false}}',
            encoding="utf-8",
        )
        result = self.run_rebuild()
        self.assertEqual(0, result.returncode, result.stderr)
        text = self.out_file.read_text(encoding="utf-8")
        self.assertIn('"alice": "a1"', text)
        self.assertNotIn(".hy2-disabled", text)

    def append_env(self, *lines):
        with self.env_file.open("a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")

    def write_user(self):
        self.users_file.write_text(
            '{"alice":{"password":"a1","disabled":false}}', encoding="utf-8"
        )

    def test_port_hop_off_keeps_single_port(self):
        self.write_user()
        result = self.run_rebuild()
        self.assertEqual(0, result.returncode, result.stderr)
        text = self.out_file.read_text(encoding="utf-8")
        self.assertIn('listen: ":443"', text)
        self.assertNotIn("-", text.splitlines()[0])

    def test_port_hop_enabled_writes_listen_range(self):
        self.write_user()
        self.append_env("PORT_HOP_ENABLED=true", "PORT_HOP_RANGE=443-1443")
        result = self.run_rebuild()
        self.assertEqual(0, result.returncode, result.stderr)
        text = self.out_file.read_text(encoding="utf-8")
        self.assertIn('listen: ":443-1443"', text)

    def test_port_hop_invalid_range_aborts_and_keeps_old_config(self):
        self.write_user()
        original = self.out_file.read_text(encoding="utf-8")
        self.append_env("PORT_HOP_ENABLED=true", "PORT_HOP_RANGE=500-600")
        result = self.run_rebuild()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("PORT_HOP_RANGE", result.stderr)
        self.assertEqual(original, self.out_file.read_text(encoding="utf-8"))

    def test_port_hop_range_not_starting_at_hy2_port_is_rejected(self):
        self.write_user()
        self.append_env("PORT_HOP_ENABLED=true", "PORT_HOP_RANGE=443-5443")
        result = self.run_rebuild()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("PORT_HOP_RANGE", result.stderr)


if __name__ == "__main__":
    unittest.main()
