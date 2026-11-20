"""面板端口弹窗：只提交用户实际改动过的端口。"""
import pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PANEL = ROOT / "lib" / "panel.sh"


class PortsModalTests(unittest.TestCase):
    """小k 反馈：只想改 VLESS，结果两个都被提交了。

    根因：applyPorts 只判断「输入框有没有值」，而弹窗打开时会用当前值
    预填，所以另一个端口永远"有值"→ 永远被一起提交。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")
        i = cls.src.index("async function applyPorts()")
        cls.body = cls.src[i : cls.src.index(chr(10) + "}", i)]

    def test_records_original_values(self):
        """打开弹窗时必须记下原值，否则无从判断"改没改"。"""
        self.assertIn("portOriginal={hy2:", self.src)

    def test_only_submits_changed_fields(self):
        self.assertIn("changedHy2", self.body)
        self.assertIn("changedVless", self.body)

    def test_no_change_is_rejected(self):
        self.assertIn("没有改动", self.body)

    def test_does_not_submit_merely_filled_field(self):
        """不能再出现「只要非空就提交」的写法。"""
        self.assertNotIn('if(hy2)jobs.push', self.body)
        self.assertNotIn('if(vless)jobs.push', self.body)

    def test_says_which_targets_changed(self):
        self.assertIn("targets.join", self.body)


if __name__ == "__main__":
    unittest.main()
