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


def shquote(value: str) -> str:
    q = chr(39)
    return q + value.replace(q, q + chr(92) + q + q) + q



class VersionExtractTests(unittest.TestCase):
    """version_extract must pull the version out of a dirty string.

    The first implementation used a greedy sed substitution; on "v2.14.0"
    it returned only "0". That is exactly how the live box printed a broken
    version line: sed never matched and the whole line fell through.
    """

    def extract(self, value: str) -> str:
        script = "set -u" + chr(10) + "source lib/core.sh" + chr(10)
        script += "version_extract " + shquote(value) + chr(10)
        return run_bash(script).stdout.strip()

    def test_plain_version(self):
        self.assertEqual("2.14.0", self.extract("v2.14.0"))

    def test_leading_v_stripped(self):
        self.assertEqual("2.12.1", self.extract("v2.12.1"))

    def test_two_part_version(self):
        self.assertEqual("2.14", self.extract("2.14"))

    def test_dirty_line_with_extra_fields(self):
        self.assertEqual("2.12.1", self.extract("v2.12.1 BuildDate: 2026"))

    def test_prefixed_label(self):
        self.assertEqual("2.12.1", self.extract("Version: v2.12.1"))

    def test_rc_suffix_truncated(self):
        self.assertEqual("2.14.0", self.extract("2.14.0-rc1"))

    def test_surrounding_whitespace(self):
        self.assertEqual("2.9.3", self.extract("  2.9.3  "))

    def test_garbage_returns_empty(self):
        self.assertEqual("", self.extract("abc"))
        self.assertEqual("", self.extract(""))

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




class UpgradeForcesKernelTests(unittest.TestCase):
    """hy2 upgrade must actually install the pinned kernel.

    repair_cmd called install_hysteria with no argument, so force defaulted
    to 0 and the "already installed" branch returned early -- upgrade updated
    the scripts but left the old kernel running forever. Observed on the live
    box: hy2 status said "可升级到 v2.14.0" right after a successful upgrade.
    """

    def test_repair_cmd_accepts_force_flag(self):
        src = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8")
        body = src[src.index("repair_cmd() {"):]
        self.assertIn("force_kernel", body[:400])

    def test_repair_cmd_passes_flag_to_install(self):
        src = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8")
        self.assertIn("install_hysteria " + chr(34) + "$force_kernel" + chr(34), src)

    def test_upgrade_command_forces_kernel(self):
        src = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn("upgrade)    repair_cmd 1", src)

    def test_repair_dispatch_forwards_argument(self):
        """repair 必须把第二个参数传给 repair_cmd。

        真正的升级链路是 bin/hy2.sh -> bash 新版 hy2.sh repair 1 ->
        repair 分支。第一轮我只改了 upgrade) 分支，结果根本走不到 ——
        hy2 upgrade 在 bin/hy2.sh 第 13 行就被拦截了，dispatch 里的
        upgrade) 分支对用户命令完全不可达。真机上因此白等了一轮。
        """
        src = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        line = [l for l in src.splitlines() if l.strip().startswith("repair)")]
        self.assertTrue(line, "找不到 repair dispatch")
        self.assertIn("${2:-", line[0], "repair 分支没转发参数")

    def test_bin_entrypoint_passes_force(self):
        """bin/hy2.sh 重新执行新版 hy2.sh 时必须带 1。"""
        src = (ROOT / "bin" / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn('bash "$tmp/hy2.sh" repair 1', src)


    def test_plain_repair_does_not_force_kernel(self):
        """hy2 repair 是「补缺失」，不该顺手换掉用户当前内核。"""
        src = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        import re
        line = [l for l in src.splitlines() if l.strip().startswith("repair)")]
        self.assertTrue(line, "找不到 repair dispatch")
        self.assertNotIn("repair_cmd 1", line[0])


class AlreadyInstalledLogTests(unittest.TestCase):
    """install_hysteria 的「已存在」日志曾经是空的。

    hysteria version 先打 ASCII banner，版本行在很后面，head -1 只拿到空行。
    """

    def test_uses_version_helper_not_head(self):
        src = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        body = src[src.index("install_hysteria() {"):]
        head = body[: body.index("local version tag arch")]
        self.assertIn("hysteria_installed_version", head)
        # 只看非注释行 —— 注释里提到 head -1 是在解释为什么不用它
        code = [l for l in head.splitlines() if not l.lstrip().startswith("#")]
        self.assertFalse(
            any("hysteria version" in l and "head -1" in l for l in code),
            "已存在分支不许再用 head -1 取版本（只会拿到 banner 空行）",
        )



class BootstrappingTests(unittest.TestCase):
    """hy2 upgrade runs the ALREADY INSTALLED bin/hy2.sh, not the new one.

    That file is the one that decides which arguments the freshly downloaded
    hy2.sh receives. Editing bin/hy2.sh therefore cannot fix the upgrade that
    is happening right now -- the running copy still has the old argument.
    On the live box this showed up as two consecutive upgrades leaving the
    kernel at v2.12.1 while status kept advertising the upgrade.

    install_hysteria must therefore compare versions itself instead of
    trusting a force flag from the caller.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        cls.body = cls.src[cls.src.index("install_hysteria() {"):]
        cls.head = cls.body[: cls.body.index("local version tag arch")]

    def test_compares_installed_against_target(self):
        self.assertIn("version_is_newer", self.head)
        self.assertIn("hysteria_installed_version", self.head)

    def test_upgrades_when_installed_is_older(self):
        self.assertIn("Hysteria 需要升级", self.head)

    def test_still_skips_when_already_current(self):
        self.assertIn("Hysteria 已是最新", self.head)

    def test_force_no_longer_skips_comparison(self):
        """force=1 不再绕过版本比较（否则每次 upgrade 都白下 25MB）。"""
        self.assertNotIn(chr(34) + "$force" + chr(34) + " != " + chr(34) + "1" + chr(34), self.head)

    def test_repair_dispatch_falls_back_to_upgrade_flag(self):
        """兜底：旧版 bin 传裸 repair 时，靠 HY2_UPGRADE_BANNER 认出这是升级。"""
        src = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        line = [l for l in src.splitlines() if l.strip().startswith("repair)")]
        self.assertTrue(line)
        self.assertIn("HY2_UPGRADE_BANNER", line[0])



class PostInstallLogTests(unittest.TestCase):
    """安装成功后那行日志曾经也是空的。

    Live output was "Hysteria 已安装：" with nothing after it -- same head -1
    mistake as the already-installed branch, but in a different place.
    """

    def test_installed_log_uses_helper(self):
        src = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        body = src[src.index("install_hysteria() {"):]
        tail = body[body.index("bash " + chr(34) + "$script" + chr(34)):]
        self.assertIn("hysteria_installed_version", tail)
        code = [l for l in tail.splitlines() if not l.lstrip().startswith("#")]
        self.assertFalse(
            any("hysteria version" in l and "head -1" in l for l in code),
            "安装成功分支不许再用 head -1 取版本",
        )


class BackendReadyWaitTests(unittest.TestCase):
    """api_post sync 在 backend 端口还没 listen 时会打 curl (7) 报错。

    systemctl is-active 只表示进程在。Python 从启动到 bind 有 1~2 秒空档，
    live output showed "curl: (7) Failed to connect to 127.0.0.1 port 18081"。
    """

    @classmethod
    def setUpClass(cls):
        cls.core = (ROOT / "lib" / "core.sh").read_text(encoding="utf-8")
        cls.backup = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8")

    def test_helper_defined(self):
        self.assertIn("wait_backend_ready()", self.core)

    def test_helper_has_timeout(self):
        body = self.core[self.core.index("wait_backend_ready()"):]
        self.assertIn("timeout", body[:600])

    def test_repair_waits_before_sync(self):
        body = self.backup[self.backup.index("repair_cmd() {"):]
        wait = body.index("wait_backend_ready")
        sync = body.index("api_post sync")
        self.assertLess(wait, sync, "必须等端口通了再 sync")

    def test_helper_survives_missing_curl(self):
        body = self.core[self.core.index("wait_backend_ready()"):]
        seg = body[: body.index("return 1")]
        self.assertIn("command -v curl", seg)



class NoRedundantReinstallTests(unittest.TestCase):
    """hy2 upgrade 每次都传 force=1, so every upgrade re-downloaded the
    25 MB binary even when the installed version was already current.

    The live box showed exactly that at 08:22 -- already on v2.14.0,
    still reinstalled. Version comparison must win over the force flag.
    """

    @classmethod
    def setUpClass(cls):
        src = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        cls.head = src[src.index("install_hysteria() {"):]
        cls.head = cls.head[: cls.head.index("local version tag arch")]

    def test_version_check_not_gated_on_force(self):
        """比较分支不能挂在 [ "$force" != "1" ] 后面。"""
        self.assertNotIn(chr(34) + "$force" + chr(34) + " != " + chr(34) + "1" + chr(34), self.head)

    def test_upgrades_when_older(self):
        self.assertIn("version_is_newer", self.head)
        self.assertIn("Hysteria 需要升级", self.head)

    def test_skips_when_current_even_with_force(self):
        self.assertIn("Hysteria 已是最新", self.head)

    def test_explicit_reinstall_escape_hatch(self):
        """怀疑二进制损坏时仍能强制重装，但要显式要求。"""
        self.assertIn("HYSTERIA_FORCE_REINSTALL", self.head)

    def test_does_not_downgrade(self):
        """已装版本更新时跳过，不能把用户降级。"""
        self.assertNotIn("version_is_newer " + chr(34) + "$have" + chr(34), self.head)

if __name__ == "__main__":
    unittest.main()