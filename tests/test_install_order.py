import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallFlowOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "hy2.sh").read_text(encoding="utf-8")

    def test_cli_installed_before_service_start(self):
        cli = self.text.index("install_hy2_cli")
        service_start = self.text.index("systemctl restart hysteria-server.service")
        self.assertLess(
            cli,
            service_start,
            "install_hy2_cli 必须在启动服务之前执行，服务失败时 hy2 命令仍可用",
        )

    def test_incomplete_install_resumes_instead_of_dead_end(self):
        guard = self.text.index("HY2 AIO 已安装")
        window = self.text[max(0, guard - 500) : guard]
        self.assertIn(
            "repair_cmd",
            window,
            "config.env 存在但缺少 hy2 命令时应续装（repair），不能只报已安装",
        )


if __name__ == "__main__":
    unittest.main()
