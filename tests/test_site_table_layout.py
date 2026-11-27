import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "web" / "index.html"


def panel_html() -> str:
    return PANEL.read_text(encoding="utf-8")


def rule(html: str, selector: str) -> str:
    pattern = re.escape(selector) + r"\s*\{([^}]*)\}"
    return ";".join(re.findall(pattern, html))


def decl(body: str, prop: str) -> str:
    m = re.search(re.escape(prop) + r"\s*:\s*([^;}]+)", body)
    return m.group(1).strip() if m else ""


class HostNameEllipsisTests(unittest.TestCase):
    """长域名把第一列挤成 23px、折成 13 行、整行 273px 高。

    根因是 .dest-host 用了 word-break:break-all（允许任意字符间断行），
    而站点表 10 列平分 617px，第一列只剩两个字符宽。
    """

    def test_no_break_all_on_host(self):
        body = rule(panel_html(), ".dest-host")
        self.assertNotEqual("break-all", decl(body, "word-break"),
                            "word-break:break-all 会把域名折成竖排")

    def test_host_is_single_line_with_ellipsis(self):
        body = rule(panel_html(), ".dest-host")
        self.assertEqual("nowrap", decl(body, "white-space"))
        self.assertEqual("hidden", decl(body, "overflow"))
        self.assertEqual("ellipsis", decl(body, "text-overflow"))

    def test_host_has_max_width(self):
        body = rule(panel_html(), ".dest-host")
        self.assertIn("max-width", body, "需要上限否则长域名会吃掉整表宽度")

    def test_site_columns_have_min_width(self):
        html = panel_html()
        self.assertIn("#trafficSiteTable", html)
        self.assertRegex(html, r"#trafficSiteTable\s+th:nth-child\(1\)[^{]*\{[^}]*min-width")


class SiteDetailExpandTests(unittest.TestCase):
    """点击域名在行下方展开详情行（占满整行，不挤压其他列）。"""

    @classmethod
    def setUpClass(cls):
        cls.html = panel_html()

    def test_toggle_function_exists(self):
        self.assertIn("function toggleSiteDetail(", self.html)

    def test_host_click_bound(self):
        self.assertIn("hostTd.onclick", self.html)

    def test_title_shows_full_host(self):
        """悬停能看到完整域名，否则省略号后无从得知。"""
        self.assertIn('title:host+"（点击展开）"', self.html)
        self.assertIn('title:host+"（点击展开）"'.replace('"（点击展开）"', ""), self.html)

    def test_detail_row_spans_all_columns(self):
        self.assertIn("colSpan:10", self.html)

    def test_detail_row_does_not_squeeze_columns(self):
        """详情必须是独立 tr，不能塞进原来的 host 单元格里。"""
        self.assertIn('el("tr",{className:"site-detail"}', self.html)
        self.assertIn("tr.after(detail)", self.html)

    def test_click_again_collapses(self):
        block = self.html[self.html.index("function toggleSiteDetail(") :]
        block = block[: block.index("function renderSiteRows(")]
        self.assertIn('classList.contains("site-detail")', block)
        self.assertIn(".remove()", block)

    def test_only_one_detail_open_at_a_time(self):
        block = self.html[self.html.index("function toggleSiteDetail(") :]
        block = block[: block.index("function renderSiteRows(")]
        self.assertIn('querySelectorAll(".site-detail")', block)

    def test_detail_uses_two_column_grid(self):
        """9 个字段竖排会到 260px 高，两列并排压到约 150px。"""
        body = rule(self.html, ".site-detail-inner dl")
        cols = decl(body, "grid-template-columns")
        self.assertEqual("auto 1fr auto 1fr", cols)


class SiteDetailContentTests(unittest.TestCase):
    def test_detail_lists_key_fields(self):
        block = panel_html()[panel_html().index("function toggleSiteDetail(") :]
        block = block[: block.index("function renderSiteRows(")]
        for label in ("完整域名", "IP", "端口", "合计", "访问次数", "占比"):
            self.assertIn(label, block, f"详情缺少字段：{label}")


if __name__ == "__main__":
    unittest.main()