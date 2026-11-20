import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_cpu_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class CpuSamplingTests(unittest.TestCase):
    """CPU 一直显示 0% 的根因是采样窗口太窄。

    老实现固定 time.sleep(0.12)：在 100Hz 内核上 120ms 每个核只有 12 个
    jiffies，1% 的真实负载折算下来才 0.12 jiffies —— 四舍五入永远是 0.0%。
    小机器上常驻进程的 1~2% 完全测不出来，面板长期显示 0%。

    新实现改成「距上次调用的增量」，采集周期 60s 就有 6000 jiffies/核，
    分辨率提高两个数量级。
    """

    def setUp(self):
        self.ns = load_backend_namespace()
        # 每个用例都重置基线，避免用例之间互相污染
        self.ns["_cpu_samples"].clear()

    def test_returns_float_in_range(self):
        value = self.ns["cpu_percent"]()
        self.assertIsInstance(value, float)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 100.0)

    def test_first_call_establishes_baseline(self):
        value = self.ns["cpu_percent"]()
        self.assertIn("last", self.ns["_cpu_samples"])
        self.assertIsNotNone(value)

    def test_repeated_fast_calls_do_not_hard_zero(self):
        """用户连点按钮会连续触发 collect，间隔可能只有几百毫秒。

        旧实现每次都开一个 120ms 的新窗口；小机器上一核 12 jiffies，
        只要有点波动就会算成 0.0%。新实现改为沿用上次读数。
        这里断言的是「不会给出一个不可信的 0」，而不是「两次必须相等」——
        后者在旧实现上也成立（大家都是 0），是个假阳性测试。
        """
        loaded = self.ns["cpu_percent"](window_seconds=1.5)
        # 制造一点真实负载再紧接着调，保证基线读数不是 0
        deadline = time.time() + 0.5
        while time.time() < deadline:
            sum(range(20000))
        quick = self.ns["cpu_percent"]()  # 间隔远小于 _CPU_MIN_WINDOW
        self.assertGreater(
            max(loaded, quick), 0.0, "连续快速调用时仍给出恒定的 0%"
        )
        # 短窗口内 quick 应当沿用上次读数（last_percent），而不是重新开一个
        # 窄窗口算出 0 或 100。这里不能断言 loaded == quick ——
        # cpu_percent(window) 在增量过小时会保留更早的 last_percent，
        # 两者本就可能不同（真机全量跑时被这条断言误伤过）。
        # 要断言的是：quick 落在可信区间，且不是硬零。
        self.assertGreater(quick, 0.0, "短窗口读数退化成硬零")
        self.assertLessEqual(quick, 100.0, "短窗口读数越界")
        self.assertAlmostEqual(
            quick,
            self.ns["_cpu_samples"].get("last_percent", quick),
            places=6,
            msg="短窗口内应沿用上次读数",
        )

    def test_min_window_constant_exists(self):
        self.assertGreaterEqual(self.ns["_CPU_MIN_WINDOW"], 1.0)

    def test_counter_read_returns_monotonic_totals(self):
        total1, idle1 = self.ns["read_cpu_counters"]()
        total2, idle2 = self.ns["read_cpu_counters"]()
        self.assertGreater(total2, 0)
        self.assertGreaterEqual(total2, total1)
        self.assertGreaterEqual(idle2, idle1)
        self.assertLessEqual(idle1, total1)

    def test_idle_includes_iowait(self):
        """idle 必须含 iowait 列：等磁盘的时候 CPU 并没在算，
        不计入 idle 会把 IO 等待算成 CPU 忙（与 top 口径不一致）。"""
        source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        block = source[source.index("def read_cpu_counters") :]
        block = block[: block.index("\ndef ")]
        self.assertIn("values[4]", block)
        self.assertIn("values[3]", block)

    def test_measurable_window_catches_real_load(self):
        """跑一段真实计算，增量窗口必须能测出非零 CPU。"""
        self.ns["cpu_percent"](window_seconds=1.0)  # 先立基线
        deadline = time.time() + 2.0
        while time.time() < deadline:
            sum(range(20000))
        value = self.ns["cpu_percent"]()
        self.assertGreater(value, 0.0, "有真实负载却测出 0%，说明窗口仍然太窄")


class CpuPayloadTests(unittest.TestCase):
    """面板需要核数才能判断负载大小；缺了 cpu_cores 前端就没法换算。"""

    def test_cores_exposed_in_payload(self):
        source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn('"cpu_cores": os.cpu_count()', source)


class PanelRefreshTests(unittest.TestCase):
    """前端刷新频率与「数据有多旧」的提示。"""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "lib" / "panel.sh").read_text(encoding="utf-8")

    def test_refresh_interval_is_not_a_full_minute(self):
        # 后端 60s 采集，前端若也 60s，用户最坏要等 2 分钟才看到变化
        self.assertNotIn("setInterval(load,60000)", self.text)
        self.assertRegex(self.text, r"setInterval\([^,]+,\s*10[0-9]{3}\)")

    def test_skips_refresh_when_tab_hidden(self):
        self.assertIn("document.hidden", self.text)

    def test_shows_data_age(self):
        self.assertIn("dataAgeText", self.text)

    def test_footer_states_real_cadence(self):
        self.assertNotIn("60 秒自动刷新", self.text)
        self.assertIn("每 10 秒拉取", self.text)


if __name__ == "__main__":
    unittest.main()