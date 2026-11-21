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




class PortLockTests(unittest.TestCase):
    """端口弹窗默认锁定,点「编辑」才能改 —— 防误触。

    小k:加一个编辑按钮,不想误触改动,点击编辑那个输入框才是可编辑状态。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")

    def test_inputs_default_disabled(self):
        """两个输入框初始必须是 disabled。"""
        for input_id in ("portHy2", "portVless"):
            tag = next(
                (l2 for l2 in self.src.splitlines() if ('id="%s"' % input_id) in l2),
                None,
            )
            self.assertIsNotNone(tag, "找不到 %s 的输入框" % input_id)
            self.assertIn("disabled", tag, "%s 没有默认 disabled" % input_id)

    def test_edit_button_exists(self):
        self.assertIn('id="portEdit"', self.src)

    def test_edit_unlocks_and_save_hidden_until_edit(self):
        """保存/取消按钮在锁定态隐藏，编辑态显示。"""
        self.assertIn("setPortEditing(true)", self.src)
        # setPortEditing 里必须同时切六个元素的状态
        i = self.src.index("function setPortEditing(on)")
        body = self.src[i : self.src.index(chr(10) + "}", i)]
        for sel in ("portHy2", "portVless", "portEdit", "portCancel", "portSave", "portLockHint"):
            self.assertIn(sel, body, "setPortEditing 没处理 %s" % sel)

    def test_modal_opens_locked(self):
        """每次打开弹窗都从锁定态开始(防止上次的编辑态残留)。"""
        self.assertIn("setPortEditing(false);", self.src)

    def test_cancel_returns_to_locked(self):
        self.assertIn('$("portCancel").onclick=function(){ setPortEditing(false); }', self.src)

    def test_apply_success_returns_to_locked(self):
        """应用成功后 1.5s 自动回锁定态。"""
        self.assertIn("setTimeout(()=>setPortEditing(false),1500)", self.src)

if __name__ == "__main__":
    unittest.main()
