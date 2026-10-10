import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "cert harness needs Linux path semantics; run via WSL")
class CertReapplyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env_file = self.root / "etc/hy2-aio/config.env"
        self.env_file.parent.mkdir(parents=True)
        self.env_file.write_text(
            "DOMAIN=panel.example.com\nPANEL_PORT=443\nHY2_PORT=8443\nAPI_SECRET=test\n",
            encoding="utf-8",
        )
        self.caddyfile = self.root / "etc/caddy/Caddyfile"
        self.caddyfile.parent.mkdir(parents=True)
        self.caddyfile.write_text("panel.example.com {\n}\n", encoding="utf-8")
        self.data_dir = self.root / "var/lib/caddy"
        self.cert_acme = (
            self.data_dir
            / "certificates/acme-v02.api.letsencrypt.org-directory/panel.example.com"
        )
        self.cert_local = (
            self.data_dir / ".local/share/caddy/certificates/local/panel.example.com"
        )
        for path in (self.cert_acme, self.cert_local):
            path.mkdir(parents=True)
            (path / "panel.example.com.crt").write_text("stale\n", encoding="utf-8")
        self.trace = self.root / "trace.log"

        commands = self.root / "commands"
        commands.mkdir()
        for name, body in {
            "caddy": "exit 0\n",
            "systemctl": f'printf "systemctl %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "ss": (
                'if [ "${MOCK_SS_80:-1}" = "1" ]; then\n'
                '  printf "LISTEN 0 511 *:80 *:*\\n"\n'
                "fi\n"
                'printf "LISTEN 0 511 *:443 *:*\\n"\n'
            ),
            "sleep": f'printf "sleep %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "journalctl": f'printf "journalctl %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "openssl": (
                f'printf "openssl %s\\n" "$*" >> "{self.trace.as_posix()}"\n'
                'case "$1" in\n'
                "  s_client) cat > /dev/null; exit 0 ;;\n"
                "  x509)\n"
                '    if [ "${MOCK_CERT_KIND:-local}" = "acme" ]; then\n'
                '      printf "subject=CN = panel.example.com\\n"\n'
                '      printf "issuer=C = US, O = Lets Encrypt, CN = R11\\n"\n'
                '      printf "notAfter=Dec 31 23:59:59 2026 GMT\\n"\n'
                "    else\n"
                '      printf "subject=CN = panel.example.com\\n"\n'
                '      printf "issuer=C = US, ST = California, CN = Caddy Local Authority\\n"\n'
                '      printf "notAfter=Dec 31 23:59:59 2026 GMT\\n"\n'
                "    fi\n"
                "    exit 0 ;;\n"
                "esac\n"
                "exit 0\n"
            ),
        }.items():
            path = commands / name
            path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
            path.chmod(0o755)
        self.commands = commands

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, *, cert_kind: str, ss_80: bool = True) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PATH"] = f"{self.commands}:{env['PATH']}"
        env["MOCK_CERT_KIND"] = cert_kind
        env["MOCK_SS_80"] = "1" if ss_80 else "0"
        return subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -Eeuo pipefail
source {shlex.quote(str(ROOT / 'lib' / 'core.sh'))}
source {shlex.quote(str(ROOT / 'lib' / 'cli.sh'))}
need_root() {{ :; }}
ENV_FILE={shlex.quote(str(self.env_file))}
CADDY_FILE={shlex.quote(str(self.caddyfile))}
CADDY_DATA_DIR={shlex.quote(str(self.data_dir))}
cert_cmd
""",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_reapply_clears_stale_state_restarts_caddy_and_reports_cert(self):
        result = self._run(cert_kind="acme")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        self.assertFalse(self.cert_acme.exists())
        self.assertFalse(self.cert_local.exists())
        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("systemctl restart caddy.service", trace)
        self.assertIn("Lets Encrypt", result.stdout)
        self.assertIn("证书已签发", result.stdout)

    def test_reapply_reports_local_fallback_and_common_causes(self):
        result = self._run(cert_kind="local", ss_80=False)
        self.assertNotEqual(0, result.returncode)

        combined = result.stdout + result.stderr
        self.assertIn("TCP 80", combined)
        self.assertIn("常见原因", combined)
        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("systemctl restart caddy.service", trace)


if __name__ == "__main__":
    unittest.main()
