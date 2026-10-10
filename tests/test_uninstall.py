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
        self.bbr_modules = self.root / "etc/modules-load.d/tcp_bbr.conf"
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
        self.xray_service = self.systemd / "hy2-xray.service"
        self.reload_path = self.systemd / "hy2-aio-reload-hysteria.path"
        self.reload_service = self.systemd / "hy2-aio-reload-hysteria.service"
        self.xray_reload_path = self.systemd / "hy2-aio-reload-xray.path"
        self.xray_reload_service = self.systemd / "hy2-aio-reload-xray.service"
        self.caddy_service = self.systemd / "caddy.service"
        self.dropin_dir = self.systemd / "hysteria-server.service.d"
        self.dropin_file = self.dropin_dir / "hy2-switch.conf"
        self.cli = self.root / "usr/local/bin/hy2"
        self.cli_sbin = self.root / "usr/local/sbin/hy2"
        self.hysteria_bin = self.root / "usr/local/bin/hysteria"
        self.xray_bin = self.root / "usr/local/bin/xray"
        self.caddy_bin = self.root / "usr/local/bin/caddy"
        self.apt_list = self.root / "etc/apt/sources.list.d/caddy-stable.list"
        self.keyring = self.root / "usr/share/keyrings/caddy-stable-archive-keyring.gpg"
        self.caddy_data = self.root / "var/lib/caddy"
        self.caddy_log = self.root / "var/log/caddy"
        self.trace = self.root / "trace.log"

        for path in (
            self.caddy_dir,
            self.systemd,
            self.fail2ban_filter.parent,
            self.fail2ban_jail.parent,
            self.sysctl.parent,
            self.bbr_modules.parent,
            self.config_dir,
            self.state_dir,
            self.rollback_dir,
            self.hysteria_dir,
            self.app_dir,
            self.web_dir,
            self.access.parent,
            self.cli.parent,
            self.cli_sbin.parent,
            self.apt_list.parent,
            self.keyring.parent,
            self.caddy_data,
            self.caddy_log,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.caddyfile.write_text(
            "other.example.com {\n    respond \"keep\"\n}\n", encoding="utf-8"
        )
        self.site_file.write_text("panel.example.com {\n}\n", encoding="utf-8")
        for path in (
            self.service,
            self.hysteria_service,
            self.xray_service,
            self.reload_path,
            self.reload_service,
            self.xray_reload_path,
            self.xray_reload_service,
            self.caddy_service,
            self.fail2ban_filter,
            self.fail2ban_jail,
            self.sysctl,
            self.bbr_modules,
            self.access,
            self.cli,
            self.hysteria_bin,
            self.xray_bin,
            self.caddy_bin,
            self.apt_list,
            self.keyring,
        ):
            path.write_text("fixture\n", encoding="utf-8")
        self.dropin_dir.mkdir(parents=True, exist_ok=True)
        self.dropin_file.write_text("fixture\n", encoding="utf-8")
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
            "systemctl": (
                f'printf "systemctl %s\\n" "$*" >> "{self.trace.as_posix()}"\n'
                'case "$*" in *is-active*) exit 1 ;; esac\n'
            ),
            "caddy": f'printf "caddy %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "fail2ban-client": f'printf "fail2ban-client %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "ufw": "exit 1\n",
            "firewall-cmd": "exit 1\n",
            "apt-get": f'printf "apt-get %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "rpm": "exit 1\n",
            "dpkg": (
                f'printf "dpkg %s\\n" "$*" >> "{self.trace.as_posix()}"\n'
                'if [ "${MOCK_DPKG_OWNS:-0}" = "1" ]; then exit 0; fi\n'
                "exit 1\n"
            ),
            "id": "exit 0\n",
            "getent": "exit 0\n",
            "userdel": f'printf "userdel %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "groupdel": f'printf "groupdel %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
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
            "CADDY_DIR": self.caddy_dir,
            "CADDY_DATA_DIR": self.caddy_data,
            "CADDY_LOG_DIR": self.caddy_log,
            "CADDY_BIN": self.caddy_bin,
            "CADDY_APT_LIST": self.apt_list,
            "CADDY_APT_KEYRING": self.keyring,
            "CADDY_SERVICE_FILE": self.caddy_service,
            "HYSTERIA_BIN": self.hysteria_bin,
            "XRAY_BIN": self.xray_bin,
            "SERVICE_FILE": self.service,
            "HYSTERIA_SERVICE_FILE": self.hysteria_service,
            "XRAY_SERVICE_FILE": self.xray_service,
            "RELOAD_PATH_FILE": self.reload_path,
            "RELOAD_SERVICE_FILE": self.reload_service,
            "XRAY_RELOAD_PATH_FILE": self.xray_reload_path,
            "XRAY_RELOAD_SERVICE_FILE": self.xray_reload_service,
            "HYSTERIA_DROPIN_DIR": self.dropin_dir,
            "SELF_INSTALL": self.cli,
            "SELF_INSTALL_SBIN": self.cli_sbin,
            "HY2_FAIL2BAN_FILTER": self.fail2ban_filter,
            "HY2_FAIL2BAN_JAIL": self.fail2ban_jail,
            "HY2_SYSCTL_FILE": self.sysctl,
            "HY2_BBR_MODULES_FILE": self.bbr_modules,
        }
        return "\n".join(f'{name}={shlex.quote(str(path))}' for name, path in values.items())

    def _run_uninstall(self, *, purge: bool = False, dpkg_owns: bool = False) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PATH"] = f"{self.commands}:{self.sysctl_bin}:{env['PATH']}"
        env["HY2_YES"] = "1"
        if purge:
            env["HY2_PURGE"] = "1"
        else:
            env.pop("HY2_PURGE", None)
        env["MOCK_DPKG_OWNS"] = "1" if dpkg_owns else "0"
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

    def test_uninstall_stops_services_one_by_one(self):
        result = self._run_uninstall()
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        trace = self.trace.read_text(encoding="utf-8")
        for unit in (
            "hy2-aio.service",
            "hy2-xray.service",
            "hysteria-server.service",
            "hy2-aio-reload-hysteria.path",
            "hy2-aio-reload-xray.path",
            "caddy.service",
        ):
            self.assertIn(f"systemctl stop {unit}", trace)

    def test_uninstall_removes_everything_for_clean_reinstall(self):
        result = self._run_uninstall()
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        for path in (
            self.config_dir,
            self.state_dir,
            self.rollback_dir,
            self.hysteria_dir,
            self.app_dir,
            self.web_dir,
            self.service,
            self.hysteria_service,
            self.xray_service,
            self.reload_path,
            self.reload_service,
            self.xray_reload_path,
            self.xray_reload_service,
            self.caddy_service,
            self.dropin_dir,
            self.fail2ban_filter,
            self.fail2ban_jail,
            self.sysctl,
            self.bbr_modules,
            self.cli,
            self.access,
            self.hysteria_bin,
            self.xray_bin,
            self.caddy_bin,
            self.apt_list,
            self.keyring,
            self.caddy_dir,
            self.caddy_data,
            self.caddy_log,
        ):
            self.assertFalse(path.exists(), path)

        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("userdel hy2-aio", trace)
        self.assertIn("userdel hysteria", trace)
        self.assertIn("userdel caddy", trace)

    def test_uninstall_purges_package_managed_caddy(self):
        result = self._run_uninstall(dpkg_owns=True)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("apt-get purge -y caddy", trace)
        self.assertFalse(self.caddy_bin.exists())

    def test_purge_env_flag_stays_compatible(self):
        result = self._run_uninstall(purge=True)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertFalse(self.config_dir.exists())


if __name__ == "__main__":
    unittest.main()
