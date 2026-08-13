import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "uninstall harness needs Linux path semantics; run via WSL")
class UninstallCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.caddy_dir = self.root / "etc/caddy"
        self.systemd = self.root / "etc/systemd/system"
        self.fail2ban_filter = self.root / "etc/fail2ban/filter.d/hy2-caddy-auth.conf"
        self.fail2ban_jail = self.root / "etc/fail2ban/jail.d/hy2-caddy-auth.conf"
        self.sysctl = self.root / "etc/sysctl.d/99-hy2-aio.conf"
        self.config_dir = self.root / "etc/hy2-aio"
        self.state_dir = self.root / "var/lib/hy2-aio"
        self.rollback_dir = self.root / "var/lib/hy2-aio-rollbacks"
        self.hysteria_dir = self.root / "etc/hysteria"
        self.app_dir = self.root / "usr/local/lib/hy2-aio"
        self.web_dir = self.root / "var/www/hy2-aio"
        self.access = self.root / "root/hy2-aio-access.txt"
        self.caddyfile = self.caddy_dir / "Caddyfile"
        self.site_file = self.caddy_dir / "hy2-aio.caddy"
        self.service = self.systemd / "hy2-aio.service"
        self.hysteria_service = self.systemd / "hysteria-server.service"
        self.reload_path = self.systemd / "hy2-aio-reload-hysteria.path"
        self.reload_service = self.systemd / "hy2-aio-reload-hysteria.service"
        self.cli = self.root / "usr/local/bin/hy2"
        self.cli_sbin = self.root / "usr/local/sbin/hy2"
        self.trace = self.root / "trace.log"

        for path in (
            self.caddy_dir,
            self.systemd,
            self.fail2ban_filter.parent,
            self.fail2ban_jail.parent,
            self.sysctl.parent,
            self.config_dir,
            self.state_dir,
            self.rollback_dir,
            self.hysteria_dir,
            self.app_dir,
            self.web_dir,
            self.access.parent,
            self.cli.parent,
            self.cli_sbin.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.caddyfile.write_text(
            "{\n"
            "    servers {\n"
            "        protocols h1 h2\n"
            "    }\n"
            "}\n"
            "\n"
            f"import {self.site_file.as_posix()}\n"
            "\n"
            "other.example.com {\n"
            "    respond \"keep\"\n"
            "}\n",
            encoding="utf-8",
        )
        self.site_file.write_text("panel.example.com {\n}\n", encoding="utf-8")
        for path in (
            self.service,
            self.hysteria_service,
            self.reload_path,
            self.reload_service,
            self.fail2ban_filter,
            self.fail2ban_jail,
            self.sysctl,
            self.access,
            self.cli,
        ):
            path.write_text("fixture\n", encoding="utf-8")
        self.cli_sbin.symlink_to(self.cli)
        (self.config_dir / "config.env").write_text(
            "DOMAIN=panel.example.com\nPANEL_PORT=443\nHY2_PORT=8443\nAPI_SECRET=test\n",
            encoding="utf-8",
        )
        (self.state_dir / "data.json").write_text("{}\n", encoding="utf-8")
        (self.hysteria_dir / "config.yaml").write_text("listen: :8443\n", encoding="utf-8")
        (self.app_dir / "server.py").write_text("print('ok')\n", encoding="utf-8")
        (self.web_dir / "index.html").write_text("panel\n", encoding="utf-8")

        commands = self.root / "commands"
        commands.mkdir()
        for name, body in {
            "systemctl": f'printf "systemctl %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "caddy": (
                f'printf "caddy %s\\n" "$*" >> "{self.trace.as_posix()}"\n'
                'if [ "${1:-}" = "validate" ]; then exit 0; fi\n'
            ),
            "fail2ban-client": f'printf "fail2ban-client %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "ufw": 'exit 1\n',
            "firewall-cmd": 'exit 1\n',
        }.items():
            path = commands / name
            path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
            path.chmod(0o755)
        sysctl_bin = self.root / "usr/sbin"
        sysctl_bin.mkdir(parents=True, exist_ok=True)
        (sysctl_bin / "sysctl").write_text(
            f'#!/bin/sh\nprintf "sysctl %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            encoding="utf-8",
        )
        (sysctl_bin / "sysctl").chmod(0o755)
        self.commands = commands
        self.sysctl_bin = sysctl_bin

    def tearDown(self):
        self.temporary.cleanup()

    def _assignments(self) -> str:
        values = {
            "CONFIG_DIR": self.config_dir,
            "ENV_FILE": self.config_dir / "config.env",
            "HYSTERIA_DIR": self.hysteria_dir,
            "APP_DIR": self.app_dir,
            "WEB_DIR": self.web_dir,
            "STATE_DIR": self.state_dir,
            "ROLLBACK_DIR": self.rollback_dir,
            "ACCESS_FILE": self.access,
            "CADDY_FILE": self.caddyfile,
            "CADDY_SITE_FILE": self.site_file,
            "SERVICE_FILE": self.service,
            "HYSTERIA_SERVICE_FILE": self.hysteria_service,
            "RELOAD_PATH_FILE": self.reload_path,
            "RELOAD_SERVICE_FILE": self.reload_service,
            "SELF_INSTALL": self.cli,
            "SELF_INSTALL_SBIN": self.cli_sbin,
            "HY2_FAIL2BAN_FILTER": self.fail2ban_filter,
            "HY2_FAIL2BAN_JAIL": self.fail2ban_jail,
            "HY2_SYSCTL_FILE": self.sysctl,
        }
        return "\n".join(f'{name}={shlex.quote(str(path))}' for name, path in values.items())

    def _run_uninstall(self, *, purge: bool = False) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PATH"] = f"{self.commands}:{self.sysctl_bin}:{env['PATH']}"
        env["HY2_YES"] = "1"
        if purge:
            env["HY2_PURGE"] = "1"
        else:
            env.pop("HY2_PURGE", None)
        patched = self.root / "patched"
        patched.mkdir(exist_ok=True)
        for name in ("core.sh", "install.sh", "config.sh", "cli.sh"):
            text = (ROOT / "lib" / name).read_text(encoding="utf-8")
            text = text.replace("readonly ROLLBACK_DIR", "# readonly ROLLBACK_DIR")
            text = text.replace("readonly BACKEND_HOST BACKEND_PORT", "# readonly BACKEND_HOST BACKEND_PORT")
            text = text.replace("readonly USER_MUTATION_LOCK", "# readonly USER_MUTATION_LOCK")
            (patched / name).write_text(text, encoding="utf-8")
        return subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -Eeuo pipefail
source {shlex.quote(str(patched / 'core.sh'))}
source {shlex.quote(str(patched / 'install.sh'))}
source {shlex.quote(str(patched / 'config.sh'))}
source {shlex.quote(str(patched / 'cli.sh'))}
need_root() {{ :; }}
api_post() {{ printf 'api_post %s\\n' "$*" >> {shlex.quote(str(self.trace))}; }}
{self._assignments()}
uninstall_cmd
""",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_default_uninstall_removes_service_residuals_but_keeps_data(self):
        result = self._run_uninstall()
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        self.assertFalse(self.site_file.exists())
        self.assertFalse(self.service.exists())
        self.assertFalse(self.hysteria_service.exists())
        self.assertFalse(self.reload_path.exists())
        self.assertFalse(self.reload_service.exists())
        self.assertFalse(self.fail2ban_filter.exists())
        self.assertFalse(self.fail2ban_jail.exists())
        self.assertFalse(self.sysctl.exists())
        self.assertFalse(self.app_dir.exists())
        self.assertFalse(self.web_dir.exists())
        self.assertFalse(self.cli.exists())

        self.assertTrue(self.config_dir.exists())
        self.assertTrue(self.state_dir.exists())
        self.assertTrue(self.rollback_dir.exists())
        self.assertTrue(self.hysteria_dir.exists())

        caddy_text = self.caddyfile.read_text(encoding="utf-8")
        self.assertNotIn("hy2-aio.caddy", caddy_text)
        self.assertIn("other.example.com", caddy_text)

        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("hy2-aio-reload-hysteria.path", trace)
        self.assertIn("caddy validate", trace)

    def test_purge_uninstall_also_removes_config_and_data(self):
        result = self._run_uninstall(purge=True)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertFalse(self.config_dir.exists())
        self.assertFalse(self.state_dir.exists())
        self.assertFalse(self.rollback_dir.exists())
        self.assertFalse(self.hysteria_dir.exists())
        self.assertFalse(self.access.exists())


class CaddyImportRemovalTests(unittest.TestCase):
    def test_removes_import_and_preserves_other_sites(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            root = Path(tmp)
            caddyfile = root / "Caddyfile"
            site = root / "hy2-aio.caddy"
            site.write_text("gone\n", encoding="utf-8")
            relative_caddy = caddyfile.relative_to(ROOT).as_posix()
            relative_site = site.relative_to(ROOT).as_posix()
            caddyfile.write_text(
                "{\n    servers {\n        protocols h1 h2\n    }\n}\n\n"
                f"import {relative_site}\n\n"
                "keep.example.com {\n    respond ok\n}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
set -Eeuo pipefail
source lib/core.sh
source lib/config.sh
caddyfile_remove_hy2_site {shlex.quote(relative_caddy)} {shlex.quote(relative_site)}
""",
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertFalse(site.exists())
            text = caddyfile.read_text(encoding="utf-8")
            self.assertNotIn("import ", text)
            self.assertIn("keep.example.com", text)


if __name__ == "__main__":
    unittest.main()
