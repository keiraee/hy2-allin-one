import os
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    path = ROOT / "tests" / f".tmp_nat_{os.getpid()}.sh"
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


class CleanupFunctionTests(unittest.TestCase):
    """残留链导致 Hysteria 起不来（iptables: Chain already exists）。

    日志实证：重启后 Hysteria FATAL，随后 dashboard 后端的
    traffic API / online API 全部 Connection refused。
    """

    def test_function_exists(self):
        self.assertIn("clean_hysteria_nat_rules()", core_src())

    def test_only_targets_hysteria_prefixes(self):
        """必须只匹配 HYSTERIA-PR- 和 hysteria_ 前缀，绝不能全清。"""
        src = core_src()
        start = src.index("clean_hysteria_nat_rules()")
        block = src[start : src.index("\nhysteria_nat_leftovers()", start)]
        self.assertIn("HYSTERIA-PR-", block)
        self.assertIn("hysteria_", block)
        # 禁止全清 / 危险操作
        for bad in ("iptables -F", "iptables -X\n", "iptables -P", "flush ruleset"):
            self.assertNotIn(bad, block, f"不能出现危险操作：{bad}")

    def test_removes_reference_before_chain(self):
        """先删引用再删链，否则 -X 报 Device or resource busy。"""
        src = core_src()
        block = src[src.index("clean_hysteria_nat_rules()") :]
        block = block[: block.index("\nhysteria_nat_leftovers()")]
        del_idx = block.index("-D $r")
        x_idx = block.index('-X "$r"')
        self.assertLess(del_idx, x_idx, "必须先 -D 摘引用，再 -X 删链")

    def test_leftovers_detector_exists(self):
        self.assertIn("hysteria_nat_leftovers()", core_src())


class RestartIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")

    def test_restart_cleans_before_start(self):
        body = self.src[self.src.index("restart_cmd()") :]
        body = body[: body.index("\n}\n", body.index("restart_cmd()"))]
        self.assertIn("clean_hysteria_nat_rules", body)
        # 顺序：stop -> clean -> start
        stop = body.index("systemctl stop hysteria-server.service")
        clean = body.index("clean_hysteria_nat_rules")
        start = body.index("systemctl start hysteria-server.service")
        self.assertLess(stop, clean, "必须先停服务再清链（运行中清会断在线转发）")
        self.assertLess(clean, start, "必须先清链再启动")


class HopCheckIntegrationTests(unittest.TestCase):
    """hop check 要能报告残留链并给修复建议。"""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "lib" / "network.sh").read_text(encoding="utf-8")

    def test_check_has_leftover_item(self):
        self.assertIn("hysteria_nat_leftovers", self.src)
        self.assertIn("自检 7/7", self.src)

    def test_check_suggests_restart(self):
        idx = self.src.index("自检 7/7 失败")
        tail = self.src[idx : idx + 400]
        self.assertIn("hy2 restart", tail)

    def test_old_six_item_labels_updated(self):
        """编号从 /6 改成 /7 后不能有漏改的。"""
        block = self.src[self.src.index("hop_check_cmd() {") :]
        block = block[: block.index("\nhop_cmd() {")]
        self.assertNotIn("/6 ", block, "还有 /6 的旧编号没改")


if __name__ == "__main__":
    unittest.main()