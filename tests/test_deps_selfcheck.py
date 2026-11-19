import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    path = ROOT / "tests" / f".tmp_deps_{os.getpid()}.sh"
    path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
    try:
        return subprocess.run(
            ["bash", path.relative_to(ROOT).as_posix()],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)


PRELUDE = """
set -Eeuo pipefail
source lib/core.sh
source lib/deps.sh
need_root() { :; }
"""


class DepsScanTests(unittest.TestCase):
    def test_missing_command_is_reported(self):
        # 造一个肯定不存在的命令名，验证扫描能发现缺件并带上包名
        result = run_bash(
            PRELUDE
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-a|pkg-b|pkg-c|core|small|always"\n'
            + "deps_scan\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("miss|hy2-no-such-cmd|pkg-a|core|small|always", result.stdout)

    def test_present_command_is_ok(self):
        result = run_bash(
            PRELUDE + 'DEPS_TABLE="sh|pkg-a|pkg-b|pkg-c|core|small|always"\ndeps_scan\n'
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ok|sh||core|small|always", result.stdout)

    def test_size_and_when_default_when_omitted(self):
        # 老式 5 段行也要能解析（向后兼容），默认 small / always
        result = run_bash(
            PRELUDE + 'DEPS_TABLE="sh|pkg-a|pkg-b|pkg-c|core"\ndeps_scan\n'
        )
        self.assertIn("ok|sh||core|small|always", result.stdout)


class DepsPkgNameTests(unittest.TestCase):
    def test_package_name_follows_package_manager(self):
        cases = {
            "apt": "iproute2",
            "dnf": "iproute",
            "yum": "iproute",
            "zypper": "iproute2",
        }
        for manager, expected in cases.items():
            result = run_bash(
                PRELUDE + f'PKG_MANAGER={manager}; deps_pkg_name iproute2 iproute iproute2\n'
            )
            self.assertEqual(expected, result.stdout.strip(), manager)


class DepsRequiredByFeatureTests(unittest.TestCase):
    def test_hop_tools_not_required_when_hop_disabled(self):
        result = run_bash(
            PRELUDE
            + "PORT_HOP_ENABLED=false; deps_is_required nft feature hop && echo yes || echo no\n"
        )
        self.assertEqual("no", result.stdout.strip())

    def test_hop_tools_required_when_hop_enabled(self):
        result = run_bash(
            PRELUDE
            + "PORT_HOP_ENABLED=true; deps_is_required iptables feature hop && echo yes || echo no\n"
        )
        self.assertEqual("yes", result.stdout.strip())

    def test_core_always_required(self):
        result = run_bash(
            PRELUDE + "deps_is_required python3 core always && echo yes || echo no\n"
        )
        self.assertEqual("yes", result.stdout.strip())

    def test_fail2ban_client_not_required_without_fail2ban_dir(self):
        result = run_bash(
            PRELUDE
            + "deps_is_required fail2ban-client feature fail2ban && echo yes || echo no\n"
        )
        self.assertEqual("no", result.stdout.strip())

    def test_firewalld_cmd_not_required_when_firewalld_absent(self):
        result = run_bash(
            PRELUDE
            + "deps_is_required firewall-cmd feature firewalld && echo yes || echo no\n"
        )
        self.assertEqual("no", result.stdout.strip())


class DepsAppliesOnlyToActiveFeatures(unittest.TestCase):
    """核心设计：没启用的功能，缺什么工具都不该被装、也不该报红。
    小机器上装一堆用不上的东西，是拿用户仅剩的磁盘和内存换噪音。"""

    @staticmethod
    def _table(cmd: str, when: str, level: str = "feature", size: str = "small") -> str:
        return f'DEPS_TABLE="{cmd}|pkg-x|pkg-x|pkg-x|{level}|{size}|{when}"\n'

    def test_fix_does_not_install_when_feature_off(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + "PORT_HOP_ENABLED=false\n"
            + self._table("hy2-no-such-cmd", "hop")
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd fix\n"
        )
        self.assertNotIn("INSTALLED:", result.stdout, result.stdout + result.stderr)

    def test_fix_does_install_when_feature_on(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + "PORT_HOP_ENABLED=true\n"
            + self._table("hy2-no-such-cmd", "hop")
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd fix\n"
        )
        self.assertIn("INSTALLED:pkg-x", result.stdout, result.stdout + result.stderr)

    def test_unused_missing_is_summarised_not_listed_as_error(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + "PORT_HOP_ENABLED=false\n"
            + self._table("hy2-no-such-cmd", "hop")
            + "deps_cmd check\n"
        )
        # 不再逐条报「缺失（当前功能未用到）」，只在结尾一句带过
        self.assertNotIn("缺失（当前功能未用到", result.stdout)
        self.assertNotIn("缺失（软件包", result.stdout)
        self.assertIn("已跳过", result.stdout)

    def test_unused_missing_does_not_fail_check(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + "PORT_HOP_ENABLED=false\n"
            + self._table("hy2-no-such-cmd", "hop")
            + "deps_cmd check\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_active_missing_fails_check(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + self._table("hy2-no-such-cmd", "always", level="core")
            + "deps_cmd check\n"
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("跑不起来", result.stderr + result.stdout)


class DepsSmallDiskTests(unittest.TestCase):
    """4GB 小盘机器（如 464MB/4G 的小机）不该被自动装上 firewalld+fail2ban：
    两者在 Debian 上要几百 MB 且带常驻服务，会把剩余空间和内存挤干。"""

    def _run_fix(self, free_kb: int, when: str = "always"):
        return run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + f'deps_disk_free_kb() {{ echo {free_kb}; }}\n'
            + f'DEPS_TABLE="hy2-no-such-cmd|pkg-big|pkg-big|pkg-big|feature|large|{when}"\n'
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd fix\n"
        )

    def test_large_package_installed_when_disk_is_roomy(self):
        result = self._run_fix(8388608)  # 8GB 可用
        self.assertIn("INSTALLED:pkg-big", result.stdout, result.stdout + result.stderr)

    def test_large_package_skipped_when_disk_is_tight(self):
        result = self._run_fix(524288)  # 512MB 可用
        self.assertNotIn("INSTALLED:pkg-big", result.stdout)
        self.assertIn("可用空间不足", result.stdout)

    def test_small_package_still_installed_on_tight_disk(self):
        # 只有 large 档才跳过；几 MB 的 small 档照装
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + 'deps_disk_free_kb() { echo 524288; }\n'
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-small|pkg-small|pkg-small|feature|small|always"\n'
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd fix\n"
        )
        self.assertIn("INSTALLED:pkg-small", result.stdout, result.stdout + result.stderr)

    def test_skip_does_not_mark_failure(self):
        result = self._run_fix(524288)
        self.assertEqual(0, result.returncode, result.stderr)


class DepsNoDeadWeightTests(unittest.TestCase):
    """清单里不许出现「代码根本没调用过」的命令。

    jq 曾经在 install_packages_v12 里装了整整几个版本，全仓却一次都没调用
    （JSON 解析一律 python3 -c）。小机器磁盘紧，这种纯遗留项必须挡在门外。"""

    def test_jq_not_in_dependency_table(self):
        text = (ROOT / "lib" / "deps.sh").read_text(encoding="utf-8")
        table = text[text.index("DEPS_TABLE='") : text.index("'\n", text.index("DEPS_TABLE='"))]
        cmds = [line.split("|")[0] for line in table.splitlines() if "|" in line]
        self.assertNotIn("jq", cmds, "jq 从未被调用，不该进依赖清单")

    @staticmethod
    def _install_commands() -> str:
        """只取 install_packages_v12 里以 apt-get/dnf/yum/zypper 开头的命令行，
        忽略注释（注释里会解释「为什么不再装 jq」，不能当成实际安装）。"""
        text = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        start = text.index("install_packages_v12() {")
        body = text[start : text.index("\n}\n", start)]
        return "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("#")
        )

    def test_install_no_longer_pulls_jq(self):
        self.assertNotRegex(
            self._install_commands(),
            r"(?<![\w-])jq(?![\w-])",
            "install_packages_v12 不该再装 jq（代码里从未调用）",
        )

    def test_install_does_not_preinstall_firewall_stack(self):
        cmds = self._install_commands()
        for pkg in ("ufw", "firewalld", "fail2ban", "iptables", "nftables"):
            self.assertNotRegex(
                cmds, rf"(?<![\w-]){pkg}(?![\w-])", f"基础安装不该预装 {pkg}"
            )


class DepsDeviceProbeTests(unittest.TestCase):
    def test_prints_arch_and_memory(self):
        result = run_bash(PRELUDE + "deps_print_device\n")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("架构", result.stdout)
        self.assertIn("内存", result.stdout)

    def test_unsupported_arch_is_warned(self):
        # 只盖 uname，其余走真实命令，避免 mock 掉 awk 导致 /proc/meminfo 解析走空
        result = run_bash(
            PRELUDE + "uname() { echo riscv64; }\ndeps_print_device\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("riscv64", result.stdout)
        self.assertIn("不在官方二进制覆盖范围", result.stderr)


class DepsEntryGuardTests(unittest.TestCase):
    """新命令必须同时挂到两处入口：根引导脚本 hy2.sh 和安装后的 bin/hy2.sh。
    d90e582 就是漏了后者，hop 只有菜单能用、命令行全落 usage。"""

    def test_both_entrypoints_dispatch_deps(self):
        for rel in ("hy2.sh", "bin/hy2.sh"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertRegex(
                text,
                r"(?m)^\s*deps\)\s+deps_cmd\s",
                f"{rel} 缺少 deps 命令分发",
            )

    def test_both_entrypoints_load_deps_module(self):
        root_script = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn('"lib/deps.sh"', root_script)
        installed = (ROOT / "bin" / "hy2.sh").read_text(encoding="utf-8")
        self.assertIn('source "${MODULES_DIR}/lib/deps.sh"', installed)

    def test_usage_documents_deps(self):
        for rel in ("hy2.sh", "bin/hy2.sh"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("hy2 deps", text, rel)


if __name__ == "__main__":
    unittest.main()