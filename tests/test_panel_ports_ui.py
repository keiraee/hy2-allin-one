"""面板端口弹窗：逐行编辑 + 防误触。

两轮迭代：
1. 小k 反馈"只想改 VLESS 结果两个都被提交" → 只提交改动过的字段（PortsModalTests）
2. 小k 反馈"加个编辑按钮防误触"，第一版误解成整弹窗一把锁，
   第二版纠正为【每行独立锁定】：改哪行点哪行的「编辑」
"""
import pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PANEL = ROOT / "web" / "index.html"


class PortsModalTests(unittest.TestCase):
    """只提交实际改动过的端口（第一轮的需求，保留回归）。"""

    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")
        i = cls.src.index("async function applyPortRow(")
        cls.body = cls.src[i : i + 2000]

    def test_records_original_values(self):
        """打开弹窗时必须记下原值，否则无从判断"改没改"。"""
        self.assertIn("portOriginal={hy2:", self.src)

    def test_no_change_is_rejected(self):
        """没改动不白发请求。"""
        self.assertIn("没有改动", self.body)

    def test_says_which_target_changed(self):
        self.assertIn('target==="hy2"?"HY2":"VLESS"', self.body)


class PortLockTests(unittest.TestCase):
    """端口弹窗防误触：每一行独立锁定，点该行的「编辑」才解锁该行。

    小k 第一版反馈「加个编辑按钮」我理解成了整个弹窗一把锁，
    第二版纠正：是每个输入框（每行）单独编辑，改 HY2 不该碰 VLESS。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")

    def _input_line(self, input_id):
        return next(
            (ln for ln in self.src.splitlines() if ('id="%s"' % input_id) in ln),
            None,
        )

    def test_both_inputs_default_disabled(self):
        for input_id in ("portHy2", "portVless"):
            tag = self._input_line(input_id)
            self.assertIsNotNone(tag, "找不到 %s 的输入框" % input_id)
            self.assertIn("disabled", tag, "%s 没有默认 disabled" % input_id)

    def test_each_row_has_its_own_edit_save_cancel(self):
        """每行三个按钮：编辑/取消/应用，ID 按行命名。"""
        for prefix in ("portHy2", "portVless"):
            for suffix in ("Edit", "Cancel", "Save"):
                self.assertIn(
                    'id="%s%s"' % (prefix, suffix),
                    self.src,
                    "缺少 %s%s 按钮" % (prefix, suffix),
                )

    def test_no_modal_level_edit_button(self):
        """弹窗级的 portEdit/portSave/portCancel 不能再出现（那是第一版误解）。"""
        self.assertNotIn('id="portEdit"', self.src)
        self.assertNotIn('id="portSave"', self.src)
        self.assertNotIn('id="portCancel"', self.src)

    def test_row_editing_is_per_target(self):
        """setPortRowEditing 按 target 操作，不再整弹窗一把锁。"""
        self.assertIn("function setPortRowEditing(target,on)", self.src)
        self.assertNotIn("function setPortEditing(", self.src)

    def test_modal_opens_with_both_rows_locked(self):
        """每次打开弹窗两行都从锁定态开始。"""
        self.assertIn('setPortRowEditing("hy2",false)', self.src)
        self.assertIn('setPortRowEditing("vless",false)', self.src)

    def test_row_apply_is_per_target(self):
        self.assertIn("async function applyPortRow(target)", self.src)
        self.assertIn('applyPortRow("hy2")', self.src)
        self.assertIn('applyPortRow("vless")', self.src)

    def test_row_apply_still_skips_no_change_and_posts(self):
        """没改动不该白发请求（保留第一版的正确行为），改动走 api/ports。"""
        i = self.src.index("async function applyPortRow(")
        body = self.src[i : self.src.index("\nasync function openQr", i)]
        self.assertIn("没有改动", body)
        self.assertIn("api/ports", body)

    def test_cancel_restores_server_value(self):
        """取消要还原该行为服务器真实值，不能留用户改了一半的数字。"""
        i = self.src.index("function setPortRowEditing(")
        body = self.src[i : self.src.index("\nfunction setPortModal", i)]
        self.assertIn("portOriginal[target]=", body)
        self.assertIn("p[target]", body)

    def test_port_field_css_layout(self):
        """输入框和按钮同一行：flex 布局。"""
        self.assertIn(".port-field{display:flex", self.src)

    def test_bindings_are_per_row(self):
        """事件绑定逐行成对出现（$("portXxxEdit") 无 # 前缀）。"""
        for prefix in ("portHy2", "portVless"):
            for suffix in ("Edit", "Cancel", "Save"):
                self.assertIn(
                    "$(" + chr(34) + prefix + suffix + chr(34) + ").onclick",
                    self.src,
                )
if __name__ == "__main__":
    unittest.main()
