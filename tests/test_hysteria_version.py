import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str, keep_files: dict[str, str] | None = None):
    path = ROOT / "tests" / f".tmp_ver_{os.getpid()}.sh"
    path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
    try:
        return subprocess.run(
            ["bash", path.relative_to(ROOT).as_posix()],
            cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False,
        )
    finally:
        path.unlink(missing_ok=True)


def core_src() -> str:
    return (ROOT / "lib" / "core.sh").read_text(encoding="utf-8")


class PinnedVersionTests(unittest.TestCase):
    """默认安装版本从 2.12.1 提到 2.14.0。

    2.12.1 上实测过端口跳跃的 NAT 链残留导致启动 FATAL；2.12.3 修了同类问题
    （端口跳跃误重定向出站 UDP），2.14.0 还带了 UDP 转发性能提升。
    """

    def test_default_install_version_is_2_14_0(self):
        src = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        self.assertIn('version="${HYSTERIA_VERSION:-v2.14.0}"', src)
        self.assertNotIn("v2.12.1}", src)

    def test_usage_documents_new_default(self):
        src = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn("默认 v2.14.0", src)


class VersionCompareTests(unittest.TestCase):
    def compare(self, a: str, b: str) -> bool:
        result = run_bash(
            "set -u\nsource lib/core.sh\n"
            f'if version_is_newer "{a}" "{b}"; then echo yes; else echo no; fi\n'
        )
        return result.stdout.strip() == "yes"

    def test_newer_detected(self):
        self.assertTrue(self.compare("2.14.0", "2.12.1"))
        self.assertTrue(self.compare("2.13.0", "2.12.3"))

    def test_older_not_newer(self):
        self.assertFalse(self.compare("2.12.1", "2.14.0"))
        self.assertFalse(self.compare("2.9.1", "2.14.0"))

    def test_equal_not_newer(self):
        self.assertFalse(self.compare("2.14.0", "2.14.0"))

    def test_handles_missing_patch_component(self):
        self.assertTrue(self.compare("2.14", "2.13.9"))
        self.assertFalse(self.compare("2.13", "2.14.0"))

    def test_handles_v_prefix(self):
        self.assertTrue(self.compare("v2.14.0", "v2.12.1"))


class InstalledVersionParseTests(unittest.TestCase):
    def test_parses_version_line(self):
        script = (
            "set -u\nsource lib/core.sh\n"
            'mkdir -p /tmp/.hy2ver\n'
            'printf \'#!/bin/sh\\necho "Version:        v2.14.0"\\n\' > /tmp/.hy2ver/hysteria\n'
            "chmod +x /tmp/.hy2ver/hysteria\n"
            "HYSTERIA_BIN=/tmp/.hy2ver/hysteria; export HYSTERIA_BIN\n"
            "hysteria_installed_version\n"
            "rm -rf /tmp/.hy2ver\n"
        )
        result = run_bash(script)
        self.assertEqual("2.14.0", result.stdout.strip())

    def test_missing_binary_returns_nonzero(self):
        script = (
            "set -u\nsource lib/core.sh\n"
            "HYSTERIA_BIN=/nonexistent/hysteria; export HYSTERIA_BIN\n"
            "hysteria_installed_version && echo found || echo missing\n"
        )
        result = run_bash(script)
        self.assertEqual("missing", result.stdout.strip())


class StatusShowsVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")

    def test_status_prints_installed_version(self):
        self.assertIn("Hysteria 内核", self.src)
        self.assertIn("hysteria_installed_version", self.src)

    def test_status_hints_upgrade_without_doing_it(self):
        """只提示不自动升级 —— 换内核属于有风险操作，得用户自己决定。"""
        self.assertIn("hy2 update", self.src)
        self.assertNotIn("install_hysteria", self.src[self.src.index("status_cmd()") : self.src.index("show_cmd()")])

    def test_empty_version_does_not_abort_status(self):
        """没装 hysteria 时 status 仍要把其他信息打出来。"""
        body = self.src[self.src.index("status_cmd()") : self.src.index("show_cmd()")]
        self.assertIn("|| true", body)


class ChangelogDrivenExpectations(unittest.TestCase):
    """版本跳跃的依据要留在代码里，方便以后追溯为什么选这个版本。"""

    def test_cleanup_rationale_mentions_versions(self):
        src = core_src()
        block = src[src.index("clean_hysteria_nat_rules") - 1200 : src.index("clean_hysteria_nat_rules")]
        self.assertIn("2.12", block)

    def test_no_stale_2_12_1_default(self):
        for rel in ("lib/install.sh", "hy2.sh"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("v2.12.1}", text, f"{rel} 还留着旧默认版本")


if __name__ == "__main__":
    unittest.main()