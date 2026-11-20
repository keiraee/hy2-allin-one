import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "lib" / "panel.sh"


def panel_html() -> str:
    src = PANEL.read_text(encoding="utf-8")
    marker = "<<'HTML'\n"
    start = src.index(marker) + len(marker)
    end = src.index("\nHTML\n", start)
    return src[start:end]


def rule(html: str, selector: str) -> str:
    """取出某条选择器的所有声明，**按出现顺序合并**（后写的覆盖先写的）。

    CSS 里同一选择器可能分多条规则声明（比如先定基础样式、后面再补一条
    覆盖），只取最后一条会漏掉前面设置的属性。
    """
    pattern = re.escape(selector) + r"\s*\{([^}]*)\}"
    matches = re.findall(pattern, html)
    return ";".join(matches)


def decl(body: str, prop: str) -> str:
    m = re.search(re.escape(prop) + r"\s*:\s*([^;}]+)", body)
    return m.group(1).strip() if m else ""


class BaseFontSizeTests(unittest.TestCase):
    """正文字号 13.5px 偏小（低于 14px 的常见可读起点），已上调到 15px。"""

    def test_body_is_15px(self):
        """正文基准字号从 13.5px 提到 15px。
        注意：卡片 label 仍然用 13.5px（那是刻意的层级），所以这里只认
        :root 里的 font-size，不能全文件搜字符串。"""
        root = panel_html()[panel_html().index(":root{") :]
        root = root[: root.index("}")]
        self.assertEqual("15px", decl(root, "font-size"))
        self.assertNotIn("13.5px", decl(root, "font-size"))

    def test_body_line_height_raised(self):
        self.assertIn("line-height:1.5", panel_html())


class MetricCardTests(unittest.TestCase):
    def test_value_is_24px(self):
        self.assertIn(".metric .value{font-size:24px", panel_html())

    def test_label_and_extra_raised(self):
        html = panel_html()
        self.assertIn("font-size:13.5px;font-weight:700", html)  # label
        self.assertIn(".metric .extra{font-size:13px", html)

    def test_cards_equal_height(self):
        """grid-auto-rows:1fr + 卡片纵向弹性，避免一高一低。"""
        html = panel_html()
        self.assertIn("grid-auto-rows:1fr", html)
        body = rule(html, ".metric")
        self.assertIn("display:flex", body.replace(" ", ""))
        self.assertIn("flex-direction:column", body.replace(" ", ""))


class MetricBarTests(unittest.TestCase):
    """流量进度条必须是可见的 4px 蓝条。

    曾经为了「卡片等高」给 .bar 加了 padding-top:10px，
    但 .bar 是 border-box + height:4px，padding 把内容区压成 0px，
    里面的 i{height:100%} 跟着变 0 —— 进度条整条消失，只剩灰底「空线」。
    """

    def test_bar_has_no_vertical_padding(self):
        body = rule(panel_html(), ".bar")
        padding = decl(body, "padding")
        self.assertEqual("", padding, "不能在 .bar 自身上加 padding")
        self.assertRegex(body, r"height:\s*4px")

    def test_bar_not_shrinkable(self):
        """卡片是 flex 纵向布局，不锁住的话 .bar 可能被压扁。"""
        self.assertIn("flex:none", rule(panel_html(), ".bar"))

    def test_spacing_moved_to_previous_sibling(self):
        html = panel_html()
        # 间距挂在 .extra 的下边距上，而不是 .bar 的 padding
        self.assertIn(".metric .extra:has(+ .bar)", html)
        self.assertIn("margin-bottom:10px", rule(html, ".metric .extra:has(+ .bar)"))

    def test_bar_pushed_to_card_bottom(self):
        """等高依赖 margin-top:auto，别为了修 padding 把它弄丢。"""
        self.assertIn("margin-top:auto", rule(panel_html(), ".metric .extra+.bar"))


class TableTests(unittest.TestCase):
    def test_cell_font_is_14px(self):
        html = panel_html()
        body = rule(html, "th,td")
        self.assertEqual("14px", decl(body, "font-size"))

    def test_header_font_raised(self):
        body = rule(panel_html(), "th")
        self.assertEqual("12.5px", decl(body, "font-size"))

    def test_status_column_never_wraps(self):
        """字号放大后状态列会折行把整行撑高一倍，必须禁止换行。"""
        html = panel_html()
        self.assertIn("white-space:nowrap", rule(html, ".status-cell"))
        self.assertIn("white-space:nowrap", rule(html, ".status-active"))
        self.assertIn("min-width:180px", html)


class SmallTextTests(unittest.TestCase):
    """12px 这类小字全部上调到 13px。"""

    def test_no_12px_left_in_key_places(self):
        html = panel_html()
        for sel in (".nav-status", ".pill", ".footer", ".hint", ".user-note",
                    ".status-active", ".trend-note", ".week-card .label"):
            body = rule(html, sel)
            if body:
                self.assertEqual("13px", decl(body, "font-size"), sel)

    def test_button_raised(self):
        body = rule(panel_html(), ".btn")
        self.assertEqual("14px", decl(body, "font-size"))


class NoPreviewLeftoversTests(unittest.TestCase):
    """A/B/字号 这些实验补丁不能混进正式代码。"""

    def test_no_experiment_markers(self):
        html = panel_html()
        for marker in ("fixA", "fixB", "fixZ", "abToggle", "zToggle", "A 方案", "B 方案"):
            self.assertNotIn(marker, html, f"预览残留：{marker}")


if __name__ == "__main__":
    unittest.main()