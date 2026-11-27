"""面板 JS 绑定的元素必须真实存在。

真机 bug:第一版"逐行编辑"改版时,HTML 里删掉了 portCancel/portSave/portEdit,
但 JS 事件绑定区还留着 $("portCancel").onclick=... —— $() 返回 null,
在 null 上赋 .onclick 直接抛 TypeError,整个 <script> 中断,
末尾的 load() 永远不执行 → 面板永远卡"正在读取数据…"。

教训:改 HTML 删元素,必须同步删 JS 绑定;加这条静态扫描防复发。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "web" / "index.html"


def extract_js(src: str) -> str:
    marker = "\n<script>\n"
    i = src.index(marker) + len(marker)
    j = src.index("</script>", i)
    return src[i:j]


class BindingIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")
        cls.js = extract_js(cls.src)
        # HTML = 内联 <script> 之前的整段。注意 vendor/qrcode.min.js 的
        # 外链 <script src=...> 在前面,不能用第一个 <script> 当边界。
        # 用最后一个 <script>（内联主脚本）做边界;其之前的所有 HTML（含外链 vendor script）都算 DOM
        cls.html = cls.src[: cls.src.rindex("<script>")]

    def test_all_bound_ids_exist_in_html(self):
        """$("xxx").onclick / $("xxx").addEventListener 的 xxx 必须在 HTML 里。"""
        bound = set(re.findall(r'\$\("([A-Za-z0-9_]+)"\)\.(?:onclick|addEventListener)', self.js))
        self.assertTrue(bound, "没扫到任何绑定,提取逻辑可能坏了")
        missing = [b for b in sorted(bound) if 'id="%s"' % b not in self.html]
        self.assertEqual(missing, [], "JS 绑定了 HTML 里不存在的元素: %s" % missing)

    def test_all_dollar_accessed_ids_exist(self):
        """更广:所有裸 $("xxx") 引用的 ID 都要在 HTML 里。

        例外:if($("xxx")) 防御式写法(作者明知可能不存在)不算违规。
        """
        used = set(re.findall(r'\$\("([A-Za-z0-9_]+)"\)', self.js))
        guarded = set(re.findall(r'if\(\$\("([A-Za-z0-9_]+)"\)\)', self.js))
        missing = [
            u for u in sorted(used - guarded)
            if 'id="%s"' % u not in self.html
        ]
        self.assertEqual(missing, [], "JS 裸引用了 HTML 里不存在的 ID: %s" % missing)

    def test_dead_cancel_binding_is_gone(self):
        """当时的肇事残留不能再出现。"""
        self.assertNotIn('$("portCancel")', self.js)
        self.assertNotIn('$("portSave")', self.js)
        self.assertNotIn('$("portEdit")', self.js)

    def test_load_retry_exists(self):
        """load 失败要有自动重试,不能一次抖动就永久卡死。"""
        self.assertIn("function scheduleLoadRetry", self.js)
        self.assertIn("loadRetryCount=0", self.js)

    def test_load_called_after_bindings(self):
        """initTheme(); load(); 必须在 script 末尾(初始化顺序哨兵)。

        注意 load() 在 scheduleLoadRetry 里也有,要找最后那次调用。
        """
        self.assertIn("initTheme();", self.js)
        # 末尾两行的位置必须晚于最后一个事件绑定
        assert_pos = self.js.rindex("initTheme();")
        load_pos = self.js.rindex("load();")
        last_binding = self.js.rindex(').onclick')
        self.assertGreater(assert_pos, last_binding)
        self.assertGreater(load_pos, last_binding)


if __name__ == "__main__":
    unittest.main()
