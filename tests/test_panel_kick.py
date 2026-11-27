"""面板「踢下线」按钮 + 面板 JS 语法守护。

两个主题放一起是有原因的：确认框文案里用了 \\n 换行，如果写成真换行，
整个 <script> 的字符串就断了，面板直接白屏 —— 而这正是本次实际踩到的坑。
"""

import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "web" / "index.html"
BACKEND = ROOT / "lib" / "backend.sh"


def panel_text() -> str:
    return PANEL.read_text(encoding="utf-8")


def extract_panel_js() -> str:
    """取出 <script> 块正文（跳过 HTML 里的第一个小内联脚本）。"""
    t = panel_text()
    start = t.index("\n<script>\n") + len("\n<script>\n")
    end = t.index("</script>", start)
    return t[start:end]


class PanelScriptSyntaxTests(unittest.TestCase):
    """生成出来的面板 JS 必须语法正确，否则页面整块白屏。"""

    def test_confirmation_strings_use_literal_backslash_n(self):
        raw = PANEL.read_bytes()
        # 确认框里紧跟「？」的两个换行必须是字面 \n，不能是真换行 0x0a
        needle = "？".encode() + b"\x0a\x0a"
        self.assertNotIn(
            needle,
            raw,
            "确认框文案里出现了真换行 0x0a，会截断 JS 字符串导致白屏；"
            "应当写成字面 \\n\\n",
        )

    def test_confirmation_strings_present(self):
        t = panel_text()
        for label in ("确认禁用", "确认删除", "确认轮换", "确认把"):
            self.assertIn(label, t)

    def test_multiline_confirms_declare_connection_drop(self):
        """这几处操作都会断掉现有连接，文案必须说清楚。"""
        t = panel_text()
        cases = [
            ("确认禁用", "会被立即踢下线"),
            ("确认删除", "会立即断线"),
            ("确认轮换", "会断线"),
            ("确认把", "只断开现有连接"),
        ]
        for label, phrase in cases:
            start = t.index(label)
            block = t[start : start + 260]
            self.assertIn(phrase, block, f"{label} 的确认框没说明会断线")

    def test_js_parses_when_node_available(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node 不可用")
        js = extract_panel_js()
        tmp = ROOT / "tests" / ".jscheck.mjs"
        tmp.write_text(js, encoding="utf-8")
        try:
            result = subprocess.run(
                [node, "--check", str(tmp)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(
                0, result.returncode,
                f"面板 JS 语法错误：{result.stderr[:600]}",
            )
        finally:
            tmp.unlink(missing_ok=True)


class KickMenuWiringTests(unittest.TestCase):
    """用户行菜单必须提供独立的「踢下线」。"""

    def test_menu_item_exists(self):
        t = panel_text()
        self.assertIn('menuItem("踢下线"', t)

    def test_menu_item_calls_kick_user(self):
        self.assertRegex(panel_text(), r'menuItem\("踢下线",\s*\(\)=>kickUser\(')

    def test_menu_item_disabled_when_offline(self):
        """离线用户没有连接可断，按钮应置灰。"""
        t = panel_text()
        line = next(l for l in t.splitlines() if 'menuItem("踢下线"' in l)
        # 第三个参数是「标红」，第四个才是「置灰」。传错位置会让离线用户标红而不是禁用。
        self.assertIn("false,!user.online", line.replace(" ", ""))

    def test_kick_user_function_defined(self):
        self.assertIn("async function kickUser(username)", panel_text())

    def test_kick_user_posts_to_kick_endpoint(self):
        t = panel_text()
        start = t.index("async function kickUser(username)")
        body = t[start : start + 800]
        self.assertIn('apiPost("api/user/kick"', body)

    def test_kick_user_reports_result(self):
        t = panel_text()
        start = t.index("async function kickUser(username)")
        body = t[start : start + 900]
        self.assertIn("已踢下线", body)
        self.assertIn("result.kicked", body)


class KickEndpointTests(unittest.TestCase):
    """后端 /user/kick：只断连接，不动 users.json。"""

    @classmethod
    def setUpClass(cls):
        cls.src = BACKEND.read_text(encoding="utf-8")

    def test_route_exists(self):
        self.assertIn('if path == "/user/kick":', self.src)

    def test_not_routed_through_user_change(self):
        """kick 不改用户数据，不该走 handle_user_change 那个批量分支。"""
        block = self.src[self.src.index('if path == "/user/kick":') :]
        block = block[: block.index('if path in (')]
        self.assertNotIn("handle_user_change", block)

    def test_reuses_kick_user_safely(self):
        block = self.src[self.src.index('if path == "/user/kick":') :]
        block = block[: block.index('if path in (')]
        self.assertIn("kick_user_safely(username)", block)

    def test_validates_username(self):
        block = self.src[self.src.index('if path == "/user/kick":') :]
        block = block[: block.index('if path in (')]
        self.assertIn("USERNAME_PATTERN", block)

    def test_reports_zero_without_error(self):
        """没人可踢不算失败 —— Hysteria 没跑/用户已离线都要返回 ok。"""
        block = self.src[self.src.index('if path == "/user/kick":') :]
        block = block[: block.index('if path in (')]
        self.assertIn('"ok": True, "kicked": 0', block)




class MenuItemParamsTests(unittest.TestCase):
    """menuItem(text, handler, bad, disabled) -- bad 和 disabled 是两件事。

    The original signature had only (text, handler, bad). Passing
    !user.online as bad made offline users RED (danger colour) instead of
    greyed out -- the opposite of the intent. Both states are needed.
    """

    @classmethod
    def setUpClass(cls):
        t = panel_text()
        start = t.index("function menuItem(")
        cls.body = t[start : start + 700]

    def test_accepts_fourth_disabled_parameter(self):
        self.assertIn("disabled", self.body.split(chr(10))[0])

    def test_sets_disabled_attribute(self):
        self.assertIn("node.disabled", self.body)

    def test_adds_disabled_class(self):
        self.assertIn(chr(34) + "disabled" + chr(34), self.body)

    def test_clears_click_handler_when_disabled(self):
        self.assertIn("node.onclick=null", self.body)

    def test_disabled_style_defined(self):
        html = panel_text()
        self.assertIn(".menu button.disabled", html)

if __name__ == "__main__":
    unittest.main()