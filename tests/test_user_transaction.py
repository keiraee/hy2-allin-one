import json
import os
import subprocess
import sys
import tempfile
import time
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
    namespace = {"__name__": "hy2_aio_transaction_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class BackendUserTransactionTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.users_file = self.root / "etc/hy2-aio/users.json"
        self.config_file = self.root / "etc/hysteria/config.yaml"
        self.lock_file = self.root / "etc/hy2-aio/.users.lock"
        self.rebuild_file = self.root / "rebuild_config.py"
        self.users_file.parent.mkdir(parents=True)
        self.config_file.parent.mkdir(parents=True)
        self.users_file.write_text(
            json.dumps({"alice": {"password": "old", "disabled": False}}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        self.config_file.write_text("old generated config\n", encoding="utf-8")
        self.rebuild_file.write_text("# fixture\n", encoding="utf-8")
        self.original_users = self.users_file.read_bytes()
        self.original_config = self.config_file.read_bytes()
        self.namespace.update(
            {
                "USERS_FILE": self.users_file,
                "HYSTERIA_CONFIG": self.config_file,
                "USER_MUTATION_LOCK": self.lock_file,
                "REBUILD_FILE": self.rebuild_file,
                "HY2_OFF_FILE": self.root / "hy2.off",
                "collect": lambda: {"ok": True},
            }
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_rebuild_failure_restores_users_and_generated_config(self):
        def failed_rebuild(*_args, **_kwargs):
            self.config_file.write_text("partially rewritten\n", encoding="utf-8")
            return SimpleNamespace(returncode=1, stderr="injected rebuild failure")

        self.namespace["subprocess"] = SimpleNamespace(
            run=mock.Mock(side_effect=failed_rebuild), DEVNULL=subprocess.DEVNULL
        )
        self.namespace["restart_hysteria"] = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "injected rebuild failure"):
            self.namespace["mutate_users"](
                lambda users: users.update(
                    {"bob": {"password": "new", "disabled": False}}
                )
            )

        self.assertEqual(self.original_users, self.users_file.read_bytes())
        self.assertEqual(self.original_config, self.config_file.read_bytes())

    def test_restart_failure_restores_users_and_generated_config(self):
        def successful_rebuild(*_args, **_kwargs):
            self.config_file.write_text("new generated config\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="")

        self.namespace["subprocess"] = SimpleNamespace(
            run=mock.Mock(side_effect=successful_rebuild), DEVNULL=subprocess.DEVNULL
        )
        self.namespace["restart_hysteria"] = mock.Mock(
            side_effect=[RuntimeError("injected restart failure"), None]
        )

        with self.assertRaisesRegex(RuntimeError, "injected restart failure"):
            self.namespace["mutate_users"](
                lambda users: users.update(
                    {"bob": {"password": "new", "disabled": False}}
                )
            )

        self.assertEqual(self.original_users, self.users_file.read_bytes())
        self.assertEqual(self.original_config, self.config_file.read_bytes())

    def test_disabling_last_user_stops_hysteria_instead_of_restart(self):
        def successful_rebuild(*_args, **_kwargs):
            self.config_file.write_text("userpass: {}\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="")

        self.namespace["subprocess"] = SimpleNamespace(
            run=mock.Mock(side_effect=successful_rebuild), DEVNULL=subprocess.DEVNULL
        )
        self.namespace["request_hysteria"] = mock.Mock()
        self.namespace["restart_hysteria"] = mock.Mock()

        self.namespace["mutate_users"](
            lambda users: users["alice"].update({"disabled": True})
        )

        self.assertTrue(self.namespace["HY2_OFF_FILE"].exists())
        self.namespace["request_hysteria"].assert_called_once_with("stop")
        self.namespace["restart_hysteria"].assert_not_called()

    def test_enabling_user_while_off_does_not_start_hysteria(self):
        self.users_file.write_text(
            json.dumps({"alice": {"password": "old", "disabled": True}}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        self.namespace["HY2_OFF_FILE"].write_text("1\n", encoding="utf-8")

        def successful_rebuild(*_args, **_kwargs):
            self.config_file.write_text("userpass:\n  alice: old\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="")

        self.namespace["subprocess"] = SimpleNamespace(
            run=mock.Mock(side_effect=successful_rebuild), DEVNULL=subprocess.DEVNULL
        )
        self.namespace["request_hysteria"] = mock.Mock()
        self.namespace["restart_hysteria"] = mock.Mock()

        self.namespace["mutate_users"](
            lambda users: users["alice"].update({"disabled": False})
        )

        self.assertTrue(self.namespace["HY2_OFF_FILE"].exists())
        self.namespace["request_hysteria"].assert_not_called()
        self.namespace["restart_hysteria"].assert_not_called()


@unittest.skipIf(os.name == "nt", "CLI transaction harness requires bash and flock")
class CliUserTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config_dir = self.root / "etc/hy2-aio"
        self.hysteria_dir = self.root / "etc/hysteria"
        self.config_dir.mkdir(parents=True)
        self.hysteria_dir.mkdir(parents=True)
        self.users_file = self.config_dir / "users.json"
        self.config_file = self.hysteria_dir / "config.yaml"
        self.lock_file = self.config_dir / ".users.lock"
        self.rebuild_file = self.root / "rebuild_config"
        self.users_file.write_text(
            json.dumps({"alice": {"password": "old", "disabled": False}}, indent=2),
            encoding="utf-8",
        )
        self.config_file.write_text("old generated config\n", encoding="utf-8")
        self.rebuild_file.write_text(
            "#!/usr/bin/env bash\nprintf 'partially rewritten\\n' > \"$HYSTERIA_CONFIG\"\nexit 1\n",
            encoding="utf-8",
        )
        self.rebuild_file.chmod(0o755)
        self.original_users = self.users_file.read_bytes()
        self.original_config = self.config_file.read_bytes()

    def tearDown(self):
        self.temporary.cleanup()

    def test_cli_rebuild_failure_rolls_back_the_whole_transaction(self):
        script = f"""
set -Eeuo pipefail
source lib/user.sh
CONFIG_DIR={str(self.config_dir)!r}
HYSTERIA_DIR={str(self.hysteria_dir)!r}
USERS_FILE={str(self.users_file)!r}
HYSTERIA_CONFIG={str(self.config_file)!r}
USER_MUTATION_LOCK={str(self.lock_file)!r}
REBUILD_FILE={str(self.rebuild_file)!r}
HY2_OFF_FILE={str(self.config_dir / "hy2.off")!r}
export HYSTERIA_CONFIG
need_root() {{ :; }}
read_env() {{ :; }}
valid_name() {{ return 0; }}
chown() {{ :; }}
systemctl() {{ return 0; }}
api_post() {{ :; }}
write_access_file() {{ :; }}
show_cmd() {{ :; }}
log() {{ :; }}
warn() {{ :; }}
die() {{ printf '%s\\n' "$*" >&2; exit 1; }}
modify_user add-user bob
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.original_users, self.users_file.read_bytes())
        self.assertEqual(self.original_config, self.config_file.read_bytes())

    def test_backend_lock_blocks_cli_flock_until_transaction_finishes(self):
        held_marker = self.root / "backend-lock-held"
        release_marker = self.root / "release-backend-lock"
        cli_marker = self.root / "cli-lock-acquired"
        child_code = f"""
import time
from pathlib import Path
from tests.test_user_transaction import load_backend_namespace
namespace = load_backend_namespace()
namespace["USER_MUTATION_LOCK"] = Path({str(self.lock_file)!r})
with namespace["user_mutation_lock"]():
    Path({str(held_marker)!r}).write_text("held", encoding="utf-8")
    while not Path({str(release_marker)!r}).exists():
        time.sleep(0.02)
"""
        backend = subprocess.Popen([sys.executable, "-c", child_code], cwd=ROOT)
        cli = None
        try:
            deadline = time.monotonic() + 5
            while not held_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(held_marker.exists(), "backend did not acquire the fixture lock")

            cli = subprocess.Popen(
                [
                    "flock",
                    "-x",
                    str(self.lock_file),
                    "bash",
                    "-c",
                    f"printf acquired > {str(cli_marker)!r}",
                ],
                cwd=ROOT,
            )
            time.sleep(0.2)
            self.assertFalse(cli_marker.exists())

            release_marker.write_text("release", encoding="utf-8")
            backend.wait(timeout=5)
            cli.wait(timeout=5)
            self.assertEqual(0, backend.returncode)
            self.assertEqual(0, cli.returncode)
            self.assertTrue(cli_marker.exists())
        finally:
            release_marker.touch()
            if backend.poll() is None:
                backend.terminate()
                backend.wait(timeout=5)
            if cli is not None and cli.poll() is None:
                cli.terminate()
                cli.wait(timeout=5)

    def test_lock_path_and_permissions_are_installed_for_both_callers(self):
        core = (ROOT / "lib" / "core.sh").read_text(encoding="utf-8")
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")

        self.assertIn('USER_MUTATION_LOCK="${CONFIG_DIR}/.users.lock"', core)
        self.assertIn('chmod 0660 "$USER_MUTATION_LOCK"', core)
        self.assertIn('Path("/etc/hy2-aio/.users.lock")', backend)


if __name__ == "__main__":
    unittest.main()
