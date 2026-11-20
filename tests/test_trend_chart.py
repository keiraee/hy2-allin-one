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


def trend_block() -> str:
    """截出绘制「增量趋势」那段 JS（从 trafficTrend 取节点到函数结束）。"""
    html = panel_html()
    start = html.index('const trend=$("trafficTrend")')
    end = html.index("function buildTrafficSummary", start)
    return html[start:end]


class TrendPeakConsistencyTests(unittest.TestCase):
    """峰值标签、红点位置、纵轴顶必须是同一个口径。

    历史 bug：纵轴顶按 max(up, down) 算，但峰值标签写 up+down，
    于是标签显示 540.6 MB 比纵轴顶 519.8 MB 还高，红点也画在 519.8，
    数字和图形对不上。
    """

    def setUp(self):
        self.block = trend_block()

    def test_axis_top_is_single_line_max(self):
        self.assertIn("const maxLine=Math.max(1,...ups,...downs)", self.block,
                      "纵轴顶必须取两条线的最大值，不能取 up+down")

    def test_peak_index_uses_single_line_max(self):
        # 峰值点应基于 max(ups[i], downs[i]) 选出，而不是 ups+downs
        self.assertIn("Math.max(ups[i],downs[i])", self.block)
        self.assertNotIn("totals.reduce", self.block)

    def test_peak_label_uses_peak_value_not_sum(self):
        self.assertIn("const peakVal=Math.max(ups[peakIdx],downs[peakIdx])", self.block)
        self.assertIn("const peakLabel=bytes(peakVal)", self.block)

    def test_circle_and_label_share_same_value(self):
        """红点坐标和标签必须由同一个 peakVal 决定，否则点和数会错位。"""
        self.assertIn("peakY=y(peakVal)", self.block)
        self.assertIn('"峰值 "+peakLabel', self.block)

    def test_note_text_no_longer_sums(self):
        note = self.block[self.block.index("trend-note") :]
        self.assertIn("bytes(peakVal)", note)
        self.assertNotIn("bytes(totals[", note)

    def test_totals_variable_removed(self):
        """改完后 totals 不再被任何地方使用，不该留死代码。"""
        self.assertNotIn("const totals=", self.block)


class TrendSanityTest(unittest.TestCase):
    """用构造数据跑一遍，确认标签值 <= 纵轴顶。"""

    def test_peak_never_exceeds_axis(self):
        MB = 1e6
        ups = [1 * MB, 20.8 * MB, 3 * MB]
        downs = [5 * MB, 519.8 * MB, 9 * MB]

        max_line = max([1, *ups, *downs])
        peak_idx = 0
        for i in range(len(ups)):
            if max(ups[i], downs[i]) > max(ups[peak_idx], downs[peak_idx]):
                peak_idx = i
        peak_val = max(ups[peak_idx], downs[peak_idx])

        self.assertLessEqual(peak_val, max_line, "峰值不能超过纵轴顶")
        self.assertEqual(519.8 * MB, peak_val)
        self.assertEqual(519.8 * MB, max_line)


if __name__ == "__main__":
    unittest.main()