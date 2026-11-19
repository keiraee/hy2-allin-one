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
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-a|pkg-b|pkg-c|core"\n'
            + "deps_scan\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("miss|hy2-no-such-cmd|pkg-a|core", result.stdout)

    def test_present_command_is_ok(self):
        result = run_bash(
            PRELUDE + 'DEPS_TABLE="sh|pkg-a|pkg-b|pkg-c|core"\ndeps_scan\n'
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ok|sh||core", result.stdout)


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
    def test_firewall_tools_not_required_when_hop_disabled(self):
        result = run_bash(
            PRELUDE
            + "PORT_HOP_ENABLED=false; deps_is_required nft optional && echo yes || echo no\n"
        )
        self.assertEqual("no", result.stdout.strip())

    def test_firewall_tools_required_when_hop_enabled(self):
        result = run_bash(
            PRELUDE
            + "PORT_HOP_ENABLED=true; deps_is_required iptables optional && echo yes || echo no\n"
        )
        self.assertEqual("yes", result.stdout.strip())

    def test_core_always_required(self):
        result = run_bash(
            PRELUDE + "deps_is_required python3 core && echo yes || echo no\n"
        )
        self.assertEqual("yes", result.stdout.strip())


class DepsFixModeTests(unittest.TestCase):
    """fix 模式必须「缺什么装什么」，不能因为「当前功能未用到」就跳过——
    否则用户开了端口跳跃才发现 nft 一直没装，又得跑一次。"""

    def test_fix_installs_even_when_feature_unused(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + 'PORT_HOP_ENABLED=false\n'
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-x|pkg-x|pkg-x|optional"\n'
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd fix\n"
        )
        self.assertIn("INSTALLED:pkg-x", result.stdout, result.stdout + result.stderr)

    def test_check_mode_skips_unused_optional(self):
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + 'PORT_HOP_ENABLED=false\n'
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-x|pkg-x|pkg-x|optional"\n'
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd check\n"
        )
        self.assertIn("当前功能未用到", result.stdout)
        self.assertNotIn("INSTALLED:", result.stdout)


class DepsSmallDiskTests(unittest.TestCase):
    """4GB 小盘机器（如 512MB/4G 的日本小机）不该被自动装上 firewalld+fail2ban：
    两者在 Debian 上要几百 MB 且带常驻服务，会把剩余空间和内存挤干。"""

    def _run_fix(self, free_kb: int):
        return run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + f'deps_disk_free_kb() {{ echo {free_kb}; }}\n'
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-big|pkg-big|pkg-big|optional|large"\n'
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
        self.assertIn("跳过", result.stdout)

    def test_small_package_still_installed_on_tight_disk(self):
        # 只有 large 档才跳过；几 MB 的 small 档照装
        result = run_bash(
            PRELUDE
            + 'PKG_MANAGER="apt"\n'
            + 'deps_disk_free_kb() { echo 524288; }\n'
            + 'DEPS_TABLE="hy2-no-such-cmd|pkg-small|pkg-small|pkg-small|optional|small"\n'
            + 'pkg_install_quiet() { echo "INSTALLED:$1"; }\n'
            + "deps_cmd fix\n"
        )
        self.assertIn("INSTALLED:pkg-small", result.stdout, result.stdout + result.stderr)

    def test_skip_does_not_mark_failure(self):
        result = self._run_fix(524288)
        self.assertEqual(0, result.returncode, result.stderr)


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