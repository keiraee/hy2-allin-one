import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WelcomeAndPanelTests(unittest.TestCase):
    def test_welcome_banner_credits_author_and_repo(self):
        core = (ROOT / "lib" / "core.sh").read_text(encoding="utf-8")
        self.assertIn("print_welcome_banner()", core)
        self.assertIn("Welcome HY2", core)
        self.assertIn("@keiraee", core)
        self.assertIn("https://github.com/keiraee/hy2-allin-one.git", core)

    def test_install_and_upgrade_show_the_banner(self):
        install = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        repair = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8")
        self.assertIn("print_welcome_banner", install)
        self.assertIn("print_welcome_banner", repair)

    def test_first_install_prints_panel_password(self):
        source = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn("面板密码：${PANEL_PASS}", source)
        self.assertNotIn("面板密码：请查看", source)
        self.assertIn("hy2 panel", source)

    def test_panel_command_and_menu_show_credentials(self):
        cli = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        bootstrap = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        usage = (ROOT / "bin" / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn("panel_cmd()", cli)
        self.assertIn("面板密码：${PANEL_PASS}", cli)
        self.assertIn("查看面板账号/密码", cli)
        self.assertIn('23)', cli)
        self.assertIn("menu_call panel_cmd", cli)
        self.assertIn("hy2 panel", usage)
        self.assertRegex(usage, r"panel\)\s+panel_cmd")
        self.assertRegex(bootstrap, r"panel\)\s+panel_cmd")


if __name__ == "__main__":
    unittest.main()
