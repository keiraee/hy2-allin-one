"""从 ss 输出抠进程名的管道不能因无匹配而炸掉 set -e。

真机 bug：面板改端口提示"成功"，实际什么都没改。
根因是 port_owner 的取值管道用了永远匹配不上的 grep 正则 ——
ss 的输出行尾有大量空白且以 )) 收尾 → grep 返回 1 →
pipefail 让整条管道返回 1 → 裸赋值触发 set -e → 整个
port_cmd 静默退出（连日志都没有，所以面板只能报"成功"）。
"""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "lib" / "config.sh"


class PortOwnerParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = CONFIG.read_text(encoding="utf-8")

    # ---------- 取值表达式提取 ----------

    def _expr_for(self, marker):
        """取出 port_owner="$( ... )" 里 $( ) 之间的那段命令。"""
        for ln in self.src.splitlines():
            if marker in ln:
                rest = ln.split("$(", 1)[1].rstrip()
                if rest.endswith('"'):
                    rest = rest[:-1]
                if rest.endswith(")"):
                    rest = rest[:-1]
                return rest.strip()
        self.fail("找不到取值表达式：" + marker)

    def tcp_expr(self):
        return self._expr_for('port_owner="$(ss -Hlntp')

    def udp_expr(self):
        return self._expr_for('port_owner="$(ss -Hlunp')

    def owner_lines(self):
        return [ln for ln in self.src.splitlines() if 'port_owner="$(' in ln]

    # ---------- 静态：管道必须兜底 ----------

    def test_owner_pipe_has_fallthrough(self):
        """取值管道必须有 || true 兜底，否则无匹配即静默退出。"""
        lines = self.owner_lines()
        self.assertTrue(lines, "找不到 port_owner 取值表达式")
        for ln in lines:
            self.assertIn("|| true", ln, "port_owner 取值管道缺少 || true 兜底")

    def test_there_are_two_owner_pipes(self):
        """TCP 和 UDP 两条都要兜底，别只修一条。"""
        self.assertEqual(len(self.owner_lines()), 2)

    def test_no_unmatchable_anchor_grep_in_code(self):
        """那个永远匹配不上的 grep 正则不能再出现在【可执行代码】里。

        注释里提到它是为了说明历史，不算违规。
        """
        for ln in self.src.splitlines():
            if ln.lstrip().startswith("#"):
                continue
            self.assertNotIn(
                "grep -oE '[a-z0-9-]+\\)$'",
                ln,
                "可执行代码里仍有永远匹配不上的 grep 正则",
            )

    # ---------- 动态：awk 真的能抠出进程名 ----------

    def _run_piped(self, expr, stdin_text):
        """把表达式里的 ss 换成 cat，好把构造的样本行喂给 awk。

        被测的是 awk 抠进程名那一步：真实环境里 awk 前一级是 ss（自产输出），
        测试里没有真 ss，换成 cat 才能注入样本。
        """
        patched = expr.replace("ss -Hlntp 2>/dev/null", "cat")
        patched = patched.replace("ss -Hlunp 2>/dev/null", "cat")
        proc = subprocess.run(
            ["bash", "-c", patched],
            input=stdin_text,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()

    def test_extracts_process_name_real_ss_shape(self):
        """按真机 ss 行形状：users:(("xray",pid=...,fd=3)) + 尾部空白。"""
        expr = self.tcp_expr().replace("$new_port", "2083")
        fake = 'LISTEN 0 4096 *:2083 *:* users:(("xray",pid=1527206,fd=3))' + " " * 30 + "\n"
        got = self._run_piped(expr, fake)
        self.assertEqual(got, "xray", "抠出来的是 " + repr(got))

    def test_hysteria_udp_line(self):
        expr = self.udp_expr().replace("$new_port", "8443")
        fake = 'UNCONN 0 0 *:8443 *:* users:(("hysteria",pid=99,fd=7))' + " " * 25 + "\n"
        got = self._run_piped(expr, fake)
        self.assertEqual(got, "hysteria")

    def test_empty_result_does_not_break_set_e(self):
        """NAT 转发的端口没有监听进程，空结果不算错误（退出码 0）。

        owner_expr() 返回的是赋值号右侧那段（含尾部 || true），
        这里模拟成真实的赋值语句来跑：
            port_owner="$( ... )"
        """
        expr = self.tcp_expr().replace("$new_port", "9000")
        expr = expr.replace("ss -Hlntp 2>/dev/null", "cat")
        script = 'port_owner="$(' + expr + ')"\necho "owner=[$port_owner]"'
        proc = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            input="",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, "空结果让 set -e 退出了：" + proc.stderr)
        self.assertIn("owner=[]", proc.stdout)

    def test_other_process_still_detected(self):
        """被别的进程占用时要能报出进程名（用于冲突提示）。"""
        expr = self.tcp_expr().replace("$new_port", "2083")
        fake = 'LISTEN 0 4096 *:2083 *:* users:(("nginx",pid=5,fd=9))' + " " * 20 + "\n"
        got = self._run_piped(expr, fake)
        self.assertEqual(got, "nginx")


if __name__ == "__main__":
    unittest.main()
