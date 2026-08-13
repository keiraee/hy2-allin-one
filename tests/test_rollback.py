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

    def tearDown(self):
        self.temporary.cleanup()

    def _shell_assignments(self):
        values = {"STATE_DIR": self.state, **self.paths}
        return "\n".join(f'{name}="{path}"' for name, path in values.items())

    def _create_snapshot(self):
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -Eeuo pipefail
source lib/backup.sh
{self._shell_assignments()}
snapshot_before_change
""",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return Path(result.stdout.strip().splitlines()[-1])

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


if __name__ == "__main__":
    unittest.main()
