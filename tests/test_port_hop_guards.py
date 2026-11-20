import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    path = ROOT / "tests" / f".tmp_hop_{os.getpid()}.sh"
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
need_root() { :; }
"""


class HopRangeGuardTests(unittest.TestCase):
    def test_default_range_is_base_plus_1000(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; default_hop_range\n')
        self.assertEqual("8443-9443", result.stdout.strip())

    def test_default_range_caps_at_65535(self):
        result = run_bash(PRELUDE + 'HY2_PORT=65000; default_hop_range\n')
        self.assertEqual("65000-65535", result.stdout.strip())

    def test_default_range_fails_at_max_port(self):
        # 65535 是合法代理端口，但往后没有可跳的端口了；这里必须失败，
        # 让 hop on 能给出「先改小代理端口」的人话提示，而不是抛
        # 「结束端口必须大于开始端口」这种跟用户行为对不上的话。
        result = run_bash(PRELUDE + 'HY2_PORT=65535; default_hop_range\n')
        self.assertNotEqual(0, result.returncode)

    def test_default_range_still_works_just_below_max(self):
        result = run_bash(PRELUDE + 'HY2_PORT=65534; default_hop_range\n')
        self.assertEqual("65534-65535", result.stdout.strip())

    def test_hop_range_falls_back_to_default(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; PORT_HOP_RANGE=""; hop_range\n')
        self.assertEqual("8443-9443", result.stdout.strip())

    def test_range_must_start_at_hy2_port(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; validate_hop_range 500-600\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("必须从代理端口", result.stderr)

    def test_range_span_limit(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; validate_hop_range 8443-10444\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("跨度", result.stderr)

    def test_range_accepts_boundaries(self):
        result = run_bash(
            PRELUDE + "HY2_PORT=8443; validate_hop_range 8443-10443\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_range_rejects_malformed(self):
        result = run_bash(PRELUDE + 'HY2_PORT=8443; validate_hop_range 8443:9443\n')
        self.assertNotEqual(0, result.returncode)
        self.assertIn("格式", result.stderr)


class HopRedirectRangeTests(unittest.TestCase):
    def test_redirect_starts_after_base_port(self):
        result = run_bash(
            PRELUDE
            + 'HY2_PORT=8443; PORT_HOP_RANGE=8443-9443; hop_redirect_range\n'
        )
        self.assertEqual("8444-9443", result.stdout.strip())

    def test_redirect_rejects_bad_range(self):
        result = run_bash(
            PRELUDE
            + "HY2_PORT=8443; PORT_HOP_RANGE=500-600; hop_redirect_range\n"
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout.strip())

    def test_redirect_single_port_range_is_bare_number(self):
        # Hysteria 的 nftPortExpr/iptablesPortExpr 在 start==end 时只写单个数字，
        # 自检若拿 "8444-8444" 去 grep，规则建好了也永远匹配不上（误报）。
        result = run_bash(
            PRELUDE
            + 'HY2_PORT=8443; PORT_HOP_RANGE=8443-8444; hop_redirect_range\n'
        )
        self.assertEqual("8444", result.stdout.strip())

    def test_redirect_two_port_range_keeps_dash(self):
        result = run_bash(
            PRELUDE
            + 'HY2_PORT=8443; PORT_HOP_RANGE=8443-8445; hop_redirect_range\n'
        )
        self.assertEqual("8444-8445", result.stdout.strip())


class HopIntervalGuardTests(unittest.TestCase):
    def test_interval_accepts_bounds(self):
        for value in ("5", "3600"):
            result = run_bash(PRELUDE + f"validate_hop_interval {value}\n")
            self.assertEqual(0, result.returncode, result.stderr)

    def test_interval_rejects_below_5(self):
        result = run_bash(PRELUDE + "validate_hop_interval 4\n")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("5-3600", result.stderr)

    def test_interval_rejects_above_3600(self):
        result = run_bash(PRELUDE + "validate_hop_interval 3601\n")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("5-3600", result.stderr)


class HopSwitchTests(unittest.TestCase):
    def test_disabled_by_default(self):
        result = run_bash(PRELUDE + "PORT_HOP_ENABLED=; port_hop_enabled || echo no\n")
        self.assertEqual("no", result.stdout.strip())

    def test_truthy_values(self):
        for value in ("1", "true", "YES", "on"):
            result = run_bash(
                PRELUDE + f"PORT_HOP_ENABLED={value}; port_hop_enabled && echo yes\n"
            )
            self.assertEqual("yes", result.stdout.strip(), value)

    def test_unknown_value_is_off(self):
        result = run_bash(
            PRELUDE + "PORT_HOP_ENABLED=maybe; port_hop_enabled || echo no\n"
        )
        self.assertEqual("no", result.stdout.strip())


class HopRollbackReachabilityTests(unittest.TestCase):
    """apply_hysteria_client_settings 内部 systemctl restart 失败会返回非零。
    脚本开着 set -Eeuo pipefail，若直接裸调，回滚代码永远执行不到，
    Hysteria 会停在起不来的状态而 config.env 里还写着 PORT_HOP_ENABLED=true。
    这里从源码层面钉住「调用点必须被兜住」。"""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")

    def hop_cmd_body(self) -> str:
        start = self.text.index("hop_cmd() {")
        # 下一个顶层函数（行首顶格的 xxx() {）
        rest = self.text[start:]
        for marker in ("\nobfs_cmd() {", "\nprompt_obfs_enabled() {"):
            idx = rest.find(marker)
            if idx != -1:
                return rest[:idx]
        return rest

    def test_no_bare_apply_call_in_hop_cmd(self):
        body = self.hop_cmd_body()
        bare = [
            line.strip()
            for line in body.splitlines()
            if line.strip() == "apply_hysteria_client_settings"
        ]
        self.assertEqual(
            [],
            bare,
            "hop_cmd 里不能裸调 apply_hysteria_client_settings："
            "它失败会让 set -e 直接退出，后面的回滚判断永远执行不到",
        )

    def test_on_and_range_rollback_when_restart_fails(self):
        body = self.hop_cmd_body()
        # on 和 range 两条路径都必须把重启失败计入回滚条件
        self.assertGreaterEqual(body.count("apply_failed=1"), 2, body)
        self.assertEqual(2, body.count('[ "$apply_failed" -eq 1 ] || ! systemctl is-active'))


class HopCliEntryTests(unittest.TestCase):
    def test_installed_cli_dispatches_hop(self):
        text = (ROOT / "bin" / "hy2.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*hop\)\s+hop_cmd\s")
        self.assertIn("hy2 hop on|off", text)




class HopCheckLeftoverTests(unittest.TestCase):
    """hop check 第 7 项的判定前提：服务运行时链本来就该存在。

    真机踩到：hy2 hop check 同时输出
      "5/7 通过：iptables 重定向规则已存在"
      "7/7 失败：发现残留的重定向规则"
    —— 两条自相矛盾，把正常运行的机器判成坏的。
    原因是 7/7 只看「链是否存在」，没考虑服务正在运行。
    """

    @classmethod
    def setUpClass(cls):
        src = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        start = src.index("# 第 7 项：残留的 NAT 链")
        cls.body = src[start : start + 1400]

    def test_checks_service_state(self):
        self.assertIn("systemctl is-active", self.body)

    def test_skips_when_service_running(self):
        self.assertIn("Hysteria 正在运行", self.body)

    def test_reports_leftover_only_when_stopped(self):
        self.assertIn("服务已停止但仍有残留", self.body)

    def test_service_state_gates_the_judgement(self):
        """svc_active 必须真的作为分支条件，不能只是注释里提一句。"""
        import re
        # 找到 svc_active 被用作 if 条件的行
        self.assertRegex(
            self.body,
            r'if\s+\[\s*"\$svc_active"\s*=\s*"1"\s*\]',
            "svc_active 没有作为分支条件使用",
        )

    def test_fail_branch_requires_service_stopped(self):
        """失败分支必须在 elif（即服务未运行）里，不能在顶层。"""
        import re
        m = re.search(r'elif\s+\[\s+-z\s+"\$leftovers"\s*\].*?else', self.body, re.S)
        self.assertIsNotNone(m, "失败分支没有挂在 elif 上")

if __name__ == "__main__":
    unittest.main()