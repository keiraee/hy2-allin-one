import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "rollback shell harness requires Linux paths")
class RollbackSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "var/lib/hy2-aio"
        self.rollback_dir = self.root / "var/lib/hy2-aio-rollbacks"
        self.paths = {
            "CONFIG_DIR": self.root / "etc/hy2-aio",
            "HYSTERIA_DIR": self.root / "etc/hysteria",
            "APP_DIR": self.root / "usr/local/lib/hy2-aio",
            "WEB_DIR": self.root / "var/www/hy2-aio",
            "CADDY_FILE": self.root / "etc/caddy/Caddyfile",
            "CADDY_SITE_FILE": self.root / "etc/caddy/hy2-aio.caddy",
            "SERVICE_FILE": self.root / "etc/systemd/system/hy2-aio.service",
            "HYSTERIA_SERVICE_FILE": self.root
            / "etc/systemd/system/hysteria-server.service",
            "RELOAD_PATH_FILE": self.root
            / "etc/systemd/system/hy2-aio-reload-hysteria.path",
            "RELOAD_SERVICE_FILE": self.root
            / "etc/systemd/system/hy2-aio-reload-hysteria.service",
            "HYSTERIA_DROPIN_DIR": self.root
            / "etc/systemd/system/hysteria-server.service.d",
            "SELF_INSTALL": self.root / "usr/local/bin/hy2",
            "SELF_INSTALL_SBIN": self.root / "usr/local/sbin/hy2",
        }
        for name, path in self.paths.items():
            if name.endswith("_DIR"):
                path.mkdir(parents=True)
                (path / "fixture.txt").write_text(f"old-{name}\n", encoding="utf-8")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"old-{name}\n", encoding="utf-8")
        self.paths["SELF_INSTALL_SBIN"].unlink()
        self.paths["SELF_INSTALL_SBIN"].symlink_to(self.paths["SELF_INSTALL"])

    def tearDown(self):
        self.temporary.cleanup()

    def _shell_assignments(self):
        values = {
            "STATE_DIR": self.state,
            "ROLLBACK_DIR": self.rollback_dir,
            **self.paths,
        }
        return "\n".join(f'{name}="{path}"' for name, path in values.items())

    def _run_backup_function(self, command: str):
        return subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -Eeuo pipefail
source lib/backup.sh
die() {{ printf 'ERROR: %s\\n' "$*" >&2; exit 1; }}
{self._shell_assignments()}
{command}
""",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def _create_snapshot(self):
        result = self._run_backup_function("snapshot_before_change")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return Path(result.stdout.strip().splitlines()[-1])

    @staticmethod
    def _write_digest(snapshot: Path):
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        sidecar = Path(str(snapshot) + ".sha256")
        sidecar.write_text(digest + "\n", encoding="ascii")
        sidecar.chmod(0o600)

    def _validate(self, snapshot: Path):
        return self._run_backup_function(
            f'validate_rollback_snapshot "{snapshot}"'
        )

    def test_snapshot_is_kept_outside_the_backend_writable_state_tree(self):
        snapshot = self._create_snapshot()

        self.assertEqual(self.rollback_dir, snapshot.parent)
        self.assertFalse(self.rollback_dir.is_relative_to(self.state))
        self.assertEqual(0o700, self.rollback_dir.stat().st_mode & 0o777)
        self.assertEqual(0, self.rollback_dir.stat().st_uid)
        self.assertTrue(Path(str(snapshot) + ".sha256").is_file())

    def test_config_file_cannot_redirect_the_root_only_rollback_directory(self):
        env_file = self.root / "redirect.env"
        env_file.write_text(
            f"PANEL_PORT=443\nROLLBACK_DIR={self.state}/rollbacks\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source lib/core.sh; ENV_FILE="{env_file}"; read_env',
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("readonly", result.stderr.lower())

    def test_valid_snapshot_passes_all_pre_extract_checks(self):
        snapshot = self._create_snapshot()
        result = self._validate(snapshot)

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_snapshot_allows_an_artifact_missing_before_repair(self):
        self.paths["RELOAD_SERVICE_FILE"].unlink()

        snapshot = self._create_snapshot()
        result = self._validate(snapshot)

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_modified_snapshot_is_rejected_by_digest_check(self):
        snapshot = self._create_snapshot()
        with snapshot.open("ab") as stream:
            stream.write(b"tampered")

        result = self._validate(snapshot)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("SHA256", result.stderr)

    def test_snapshot_with_group_write_permission_is_rejected(self):
        snapshot = self._create_snapshot()
        snapshot.chmod(0o660)

        result = self._validate(snapshot)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("0600", result.stderr)

    def test_path_traversal_member_is_rejected(self):
        self.rollback_dir.mkdir(parents=True, mode=0o700)
        snapshot = self.rollback_dir / "hy2-before-20260813-120000.tar.gz"
        payload = b"owned\n"
        with tarfile.open(snapshot, "w:gz") as archive:
            member = tarfile.TarInfo("../../etc/cron.d/hy2-pwn")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        snapshot.chmod(0o600)
        self._write_digest(snapshot)

        result = self._validate(snapshot)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("成员", result.stderr)

    def test_symlink_outside_managed_paths_is_rejected(self):
        self.rollback_dir.mkdir(parents=True, mode=0o700)
        snapshot = self.rollback_dir / "hy2-before-20260813-120001.tar.gz"
        with tarfile.open(snapshot, "w:gz") as archive:
            member = tarfile.TarInfo(str(self.paths["SELF_INSTALL_SBIN"]).lstrip("/"))
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/shadow"
            archive.addfile(member)
        snapshot.chmod(0o600)
        self._write_digest(snapshot)

        result = self._validate(snapshot)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("链接", result.stderr)

    def test_special_device_member_is_rejected(self):
        self.rollback_dir.mkdir(parents=True, mode=0o700)
        snapshot = self.rollback_dir / "hy2-before-20260813-120002.tar.gz"
        with tarfile.open(snapshot, "w:gz") as archive:
            member = tarfile.TarInfo(str(self.paths["SELF_INSTALL"]).lstrip("/"))
            member.type = tarfile.FIFOTYPE
            archive.addfile(member)
        snapshot.chmod(0o600)
        self._write_digest(snapshot)

        result = self._validate(snapshot)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("类型", result.stderr)

    def test_snapshot_contains_every_repair_managed_artifact(self):
        snapshot = self._create_snapshot()
        with tarfile.open(snapshot, "r:gz") as archive:
            members = {name.rstrip("/") for name in archive.getnames()}

        for path in self.paths.values():
            expected = str(path).lstrip("/")
            self.assertIn(expected, members, expected)

    def test_snapshot_restores_files_overwritten_by_repair(self):
        snapshot = self._create_snapshot()
        targets = (
            self.paths["CADDY_SITE_FILE"],
            self.paths["RELOAD_PATH_FILE"],
            self.paths["RELOAD_SERVICE_FILE"],
            self.paths["SELF_INSTALL"],
        )
        expected = {path: path.read_text(encoding="utf-8") for path in targets}
        for path in targets:
            path.write_text("new-repair-content\n", encoding="utf-8")

        result = subprocess.run(
            ["tar", "-xzf", str(snapshot), "-C", "/"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        for path, content in expected.items():
            self.assertEqual(content, path.read_text(encoding="utf-8"), str(path))

    def test_rollback_reloads_and_restores_the_reload_path_unit(self):
        source = (ROOT / "lib/backup.sh").read_text(encoding="utf-8")
        rollback = source[source.index("rollback_cmd()") :]
        rollback = rollback[: rollback.index("\n}\n", 1) + 3]

        self.assertIn("systemctl daemon-reload", rollback)
        self.assertIn("systemctl enable hy2-aio-reload-hysteria.path", rollback)
        self.assertIn("systemctl restart hy2-aio-reload-hysteria.path", rollback)
        self.assertLess(
            rollback.index('validate_rollback_snapshot "$snapshot"'),
            rollback.index('tar -xzf "$snapshot"'),
        )


if __name__ == "__main__":
    unittest.main()
