import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateHintTests(unittest.TestCase):
    def test_menu_entry_probes_latest_release_once(self):
        cli = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        self.assertIn("refresh_update_hint()", cli)
        self.assertIn("print_update_hint", cli)
        self.assertRegex(cli, r"menu_interactive\(\)[\s\S]*refresh_update_hint")
        self.assertIn("api.github.com/repos/", cli)
        self.assertIn("/releases/latest", cli)
        self.assertIn("update-check.json", cli)
        self.assertIn("3600", cli)
        self.assertIn("--connect-timeout 2", cli)
        self.assertIn("--max-time 3", cli)
        self.assertIn("可升级", cli)
        self.assertIn("hy2 upgrade", cli)

    def test_empty_update_hint_does_not_trip_set_e(self):
        cli = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        match = re.search(r"print_update_hint\(\) \{.*?\n\}", cli, re.S)
        self.assertIsNotNone(match)
        script = f"""
set -Eeuo pipefail
UPDATE_HINT=""
{match.group(0)}
print_update_hint
echo SURVIVED
"""
        result = subprocess.run(
            ["bash", "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SURVIVED", result.stdout)

    def test_status_and_other_commands_do_not_probe(self):
        cli = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        status = cli[cli.index("status_cmd()") : cli.index("show_cmd()")]
        self.assertNotIn("refresh_update_hint", status)
        self.assertNotIn("releases/latest", status)


if __name__ == "__main__":
    unittest.main()
