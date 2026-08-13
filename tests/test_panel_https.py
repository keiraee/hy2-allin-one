import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class PanelHttpsTests(unittest.TestCase):
    def test_panel_port_validator_rejects_plain_http_port(self):
        result = run_bash(
            """
source lib/core.sh
panel_port_is_valid 443
panel_port_is_valid 8443
! panel_port_is_valid 80
! panel_port_is_valid invalid
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_read_env_rejects_legacy_port_80_configuration(self):
        result = run_bash(
            "source lib/core.sh; ENV_FILE=tests/fixtures/panel-port-80.env; read_env"
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("80", result.stderr)
        self.assertIn("HTTPS", result.stderr)

    def test_install_and_caddy_generation_enforce_https_panel_port(self):
        install = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        install_check = 'panel_port_is_valid "$PANEL_PORT"'
        config_check = 'panel_port_is_valid "${PANEL_PORT:-}"'

        self.assertIn(install_check, install)
        self.assertIn(config_check, config)
        self.assertLess(
            install.index(install_check), install.index('STATS_PORT="${HY2_STATS_PORT'),
        )
        write_caddy = config[config.index("write_caddy()") :]
        self.assertLess(write_caddy.index(config_check), write_caddy.index("install -d"))
        env_idx = write_caddy.index("\n  env \\\n")
        host_idx = write_caddy.index('BACKEND_HOST="$BACKEND_HOST"')
        self.assertLess(env_idx, host_idx)

    def test_readonly_backend_host_can_be_passed_to_child_via_env(self):
        result = run_bash(
            """
set -Eeuo pipefail
source lib/core.sh
env BACKEND_HOST="$BACKEND_HOST" BACKEND_PORT="$BACKEND_PORT" \
  python3 -c 'import os; assert os.environ["BACKEND_HOST"]=="127.0.0.1"'
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_generated_public_urls_have_no_plain_http_panel_fallback(self):
        for relative in ("lib/access.sh", "lib/backend.sh", "lib/config.sh"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn('port == "80"', source, relative)
            self.assertNotIn("f\"http://{domain}\"", source, relative)


if __name__ == "__main__":
    unittest.main()
