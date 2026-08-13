import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_detection(caddyfile: Path, *, domain: str, port: str = "443") -> subprocess.CompletedProcess:
    relative = caddyfile.relative_to(ROOT).as_posix()
    script = f"""
set -Eeuo pipefail
source lib/core.sh
source lib/config.sh
DOMAIN={shlex.quote(domain)}
PANEL_PORT={shlex.quote(port)}
WEB_DIR="/var/www/hy2-aio"
caddyfile_has_legacy_hy2_site {shlex.quote(relative)}
"""
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class CaddyLegacyDetectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.caddyfile = Path(self.temporary.name) / "Caddyfile"

    def tearDown(self):
        self.temporary.cleanup()

    def test_detects_legacy_inline_site_block(self):
        self.caddyfile.write_text(
            "panel.example.com {\n"
            "    root * /var/www/other\n"
            "}\n",
            encoding="utf-8",
        )

        result = run_detection(self.caddyfile, domain="panel.example.com")

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_detects_legacy_site_block_with_custom_port(self):
        self.caddyfile.write_text(
            "panel.example.com:8443 {\n"
            "    respond \"OK\"\n"
            "}\n",
            encoding="utf-8",
        )

        result = run_detection(self.caddyfile, domain="panel.example.com", port="8443")

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_detects_legacy_site_via_web_dir_reference(self):
        self.caddyfile.write_text(
            "other.example.com {\n"
            "    root * /var/www/hy2-aio\n"
            "}\n",
            encoding="utf-8",
        )

        result = run_detection(self.caddyfile, domain="panel.example.com")

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_dotted_domain_does_not_match_similar_hostnames(self):
        self.caddyfile.write_text(
            "aXexampleXcom {\n"
            "    respond \"unrelated\"\n"
            "}\n",
            encoding="utf-8",
        )

        result = run_detection(self.caddyfile, domain="a.example.com")

        self.assertNotEqual(0, result.returncode, result.stderr or result.stdout)

    def test_unrelated_site_is_not_flagged_as_legacy(self):
        self.caddyfile.write_text(
            "totally-unrelated.example.org {\n"
            "    respond \"OK\"\n"
            "}\n",
            encoding="utf-8",
        )

        result = run_detection(self.caddyfile, domain="panel.example.com")

        self.assertNotEqual(0, result.returncode, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
