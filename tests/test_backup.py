import os
import tarfile
import tempfile
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
    namespace = {"__name__": "hy2_aio_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

        files = {
            "etc/hy2-aio/config.env": "BACKUP_RETENTION_DAYS=14\n",
            "etc/hy2-aio/users.json": "{}\n",
            "etc/hy2-aio/client-mode.json": '{"default": {"mode": "bbr"}}\n',
            "etc/hysteria/config.yaml": "listen: :8443\n",
            "etc/hysteria/server.crt": "certificate\n",
            "etc/hysteria/server.key": "private-key\n",
            "etc/caddy/Caddyfile": "example.com {}\n",
            "usr/local/lib/hy2-aio/server.py": "# generated backend\n",
            "usr/local/lib/hy2-aio/rebuild_config.py": "# generated config builder\n",
        }
        for relative, content in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        self.namespace["BACKUP_ROOT"] = self.root
        self.namespace["BACKUP_DIR"] = self.root / "var/lib/hy2-aio/backups"
        self.namespace["DOWNLOAD_DIR"] = self.root / "var/www/hy2-aio/downloads"
        self.namespace["ENV_FILE"] = self.root / "etc/hy2-aio/config.env"

    def tearDown(self):
        self.temporary.cleanup()

    def test_backup_contains_private_key_and_omits_generated_root_access_file(self):
        backup = self.namespace["create_backup"](force=True)

        self.assertIsNotNone(backup)
        if os.name != "nt":
            self.assertEqual(0o600, backup.stat().st_mode & 0o777)
        with tarfile.open(backup, "r:gz") as archive:
            members = set(archive.getnames())
        self.assertIn("etc/hysteria/server.key", members)
        self.assertNotIn("root/hy2-aio-access.txt", members)

    def test_missing_required_private_key_fails_without_publishing_archive(self):
        (self.root / "etc/hysteria/server.key").unlink()

        with self.assertRaisesRegex(RuntimeError, "server.key"):
            self.namespace["create_backup"](force=True)

        published = list(self.namespace["BACKUP_DIR"].glob("*.tar.gz"))
        temporary = list(self.namespace["BACKUP_DIR"].glob("*.tmp"))
        self.assertEqual([], published)
        self.assertEqual([], temporary)

    def test_unreadable_required_file_is_reported_and_not_ignored(self):
        command = []

        def permission_denied(args, **_kwargs):
            command.extend(args)
            return SimpleNamespace(
                returncode=2,
                stderr="tar: etc/hysteria/server.key: Cannot open: Permission denied",
            )

        with mock.patch.object(self.namespace["subprocess"], "run", permission_denied):
            with self.assertRaisesRegex(RuntimeError, "Permission denied"):
                self.namespace["create_backup"](force=True)

        self.assertNotIn("--ignore-failed-read", command)
        self.assertEqual([], list(self.namespace["BACKUP_DIR"].glob("*")))

    def test_unchanged_daily_backup_is_not_revalidated_every_minute(self):
        backup = self.namespace["create_backup"]()

        with mock.patch.dict(
            self.namespace,
            {"validate_backup_archive": mock.Mock(side_effect=AssertionError("revalidated"))},
        ):
            reused = self.namespace["create_backup"]()

        self.assertEqual(backup, reused)

    def test_backup_endpoint_runs_exactly_one_forced_backup(self):
        calls = []

        def fake_collect(*, run_backup=True):
            calls.append(("collect", run_backup))
            return {"generated_at": "2026-08-13T00:00:00Z"}

        backup_path = Path("/var/lib/hy2-aio/backups/test.tar.gz")

        def fake_create_backup(*, force=False):
            calls.append(("backup", force))
            return backup_path

        self.namespace["collect"] = fake_collect
        self.namespace["create_backup"] = fake_create_backup

        class FakeRequest:
            path = "/backup"

            def require_api_secret(self):
                return True

            def require_same_origin(self):
                return True

            def require_rate_limit(self, *_args):
                return True

            def send_json(self, status, payload):
                self.response = (status, payload)

        request = FakeRequest()
        self.namespace["Handler"].do_POST(request)

        self.assertEqual([("collect", False), ("backup", True)], calls)
        self.assertEqual(200, request.response[0])
        self.assertEqual(str(backup_path), request.response[1]["backup"])

    def test_private_key_permissions_allow_only_owner_and_backend_group_to_read(self):
        core = (ROOT / "lib" / "core.sh").read_text(encoding="utf-8")
        cert = (ROOT / "lib" / "cert.sh").read_text(encoding="utf-8")
        systemd = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")

        self.assertIn('chown hysteria:hysteria "$HYSTERIA_CERT" "$HYSTERIA_KEY"', core)
        self.assertIn('chmod 0640 "$HYSTERIA_KEY"', core)
        self.assertIn('chown hysteria:hysteria "$HYSTERIA_CERT" "$HYSTERIA_KEY"', cert)
        self.assertIn('chmod 0640 "$HYSTERIA_KEY"', cert)
        self.assertIn("SupplementaryGroups=hysteria caddy", systemd)


if __name__ == "__main__":
    unittest.main()
