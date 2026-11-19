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