"""hy2 port 命令 + 面板端口设置。

背景：运营商 DPI 对某些端口做选择性干扰（实测 8443 TLS 握手被掐、
2083 正常）。原来改端口只能手工 sed config.env + 手动 rebuild，
而且 hy2 restart 不重建 xray.json，改完经常「不生效」。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "lib" / "config.sh"
BACKEND = ROOT / "lib" / "backend.sh"
PANEL = ROOT / "lib" / "panel.sh"
CLI = ROOT / "lib" / "cli.sh"
HY2SH = ROOT / "hy2.sh"


class PortCmdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = CONFIG.read_text(encoding="utf-8")
        start = cls.src.index("port_cmd()")
        cls.body = cls.src[start : start + 12000]

    def test_defined(self):
        self.assertIn("port_cmd()", self.src)

    def test_show_subcommand(self):
        self.assertIn('show|status|"")', self.body)

    def test_both_targets(self):
        self.assertIn('hy2|vless)', self.body)

    def test_conflict_checks(self):
        """与面板/统计/内部端口冲突要拦。"""
        self.assertIn("BACKEND_PORT", self.body)
        self.assertIn("端口冲突", self.body)

    def test_rejects_used_port(self):
        self.assertIn("tcp_port_is_used", self.body)
        self.assertIn("port_is_used", self.body)

    def test_triggers_rebuild_via_sync(self):
        """改完必须触发重建 —— 否则 xray.json 不更新（真踩过的坑）。"""
        self.assertIn("api_post sync", self.body)

    def test_restarts_with_nat_cleanup(self):
        """HY2 重启必须走 stop→clean→start（防 Chain already exists）。"""
        self.assertIn("clean_hysteria_nat_rules", self.body)

    def test_range_form_enables_hopping(self):
        """hy2 port hy2 8443-9443 应写入 PORT_HOP_RANGE + ENABLED。"""
        self.assertIn("PORT_HOP_RANGE", self.body)
        self.assertIn("PORT_HOP_ENABLED true", self.body)

    def test_reminds_reimport(self):
        """端口变了订阅内容就变了，必须提醒用户重新导入。"""
        self.assertIn("重新导入订阅", self.body)

    def test_dispatch_wired(self):
        for f in (HY2SH, ROOT / "bin" / "hy2.sh"):
            text = f.read_text(encoding="utf-8")
            self.assertRegex(text, r"port\)\s+port_cmd")


class PortControlScriptTests(unittest.TestCase):
    """hysteria-control.sh 的 port: 前缀 —— 面板（无特权）改端口的通道。"""

    @classmethod
    def setUpClass(cls):
        cls.src = CONFIG.read_text(encoding="utf-8")

    def test_control_understands_port_prefix(self):
        self.assertIn('port:*)', self.src)
        self.assertIn("hy2 port", self.src)

    def test_parses_target_and_value(self):
        self.assertIn("cut -d:", self.src)


class BackendPortApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BACKEND.read_text(encoding="utf-8")

    def test_route_exists(self):
        self.assertIn('if path == "/ports":', self.src)

    def test_helper_validates_target(self):
        body = self.src[self.src.index("def request_port_change"):]
        self.assertIn('("hy2", "vless")', body)

    def test_helper_rejects_bad_chars(self):
        """cmd 文件内容会进 shell，必须白名单字符。"""
        body = self.src[self.src.index("def request_port_change"):]
        self.assertRegex(body, r"fullmatch.*\[0-9\]")

    def test_data_json_exposes_ports(self):
        body = self.src[self.src.index("def collect("):]
        self.assertIn('"ports"', body)
        self.assertIn('"hy2"', body)
        self.assertIn('"vless"', body)


class PanelPortUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")

    def test_modal_exists(self):
        self.assertIn('id="portModal"', self.src)
        self.assertIn('id="portHy2"', self.src)
        self.assertIn('id="portVless"', self.src)

    def test_button_in_services_section(self):
        self.assertIn('id="portBtn"', self.src)

    def test_js_calls_api(self):
        self.assertIn('apiPost("api/ports"', self.src)

    def test_js_shows_slow_hint(self):
        """改端口要重建+重启，UI 必须先说会断线。"""
        self.assertIn("短暂断开", self.src)

    def test_warns_reimport(self):
        self.assertIn("重新导入订阅", self.src)


class RestartSyncsPortTests(unittest.TestCase):
    """hy2 restart 要能发现 XRAY_PORT 与 xray.json 不一致并触发重建。

    手工 sed config.env 后 restart 不生效 —— 因为 xray.json 只在用户
    变更时重建。这个坑在换端口绕干扰时真实踩过。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = CLI.read_text(encoding="utf-8")
        start = cls.src.index("restart_cmd()")
        cls.body = cls.src[start : start + 2600]

    def test_compares_ports(self):
        self.assertIn("XRAY_PORT", self.body)

    def test_triggers_sync_on_mismatch(self):
        self.assertIn("api_post sync", self.body)

    def test_rebuild_before_xray_start(self):
        body = self.body
        sync = body.index("api_post sync")
        xray = body.index("restart_hy2_xray_or_die")
        self.assertLess(sync, xray, "必须先重建再拉 Xray")




class HopRangeConflictTests(unittest.TestCase):
    """VLESS 端口不能落在 HY2 端口跳跃范围内。

    小k 实测踩到的隐藏 bug：把 VLESS 换到 HY2 跳跃区间内的端口时，
    HY2 的 NAT REDIRECT 规则覆盖整段 dport，两个服务端口撞在一起，
    排查困难。现在换端口时自动识别并提示。
    """

    @classmethod
    def setUpClass(cls):
        src = CONFIG.read_text(encoding="utf-8")
        start = src.index("# HY2 端口跳跃的 UDP 范围与 VLESS 的 TCP 端口必须错开")
        cls.body = src[start : start + 2000]

    def test_checks_vless_against_hop_range(self):
        self.assertIn("落在 HY2 端口跳跃范围", self.body)

    def test_checks_new_range_against_vless(self):
        self.assertIn("包含当前 VLESS 端口", self.body)

    def test_reads_hop_range_from_env(self):
        self.assertIn("PORT_HOP_RANGE", self.body)

    def test_suggests_alternative_port(self):
        """报错要给可直接复制的下一步命令，不能只说"冲突了"。"""
        self.assertIn("sudo hy2 port vless", self.body)

    def test_only_checks_when_hopping_enabled(self):
        """端口跳跃关闭时不该拿 PORT_HOP_RANGE 的历史值误拦。

        实测踩到：hy2 hop off 之后 PORT_HOP_ENABLED=false 但 env 里
        PORT_HOP_RANGE 可能还留着，检查逻辑照旧拦人。
        """
        self.assertIn("port_hop_enabled", self.body)

    def test_handles_single_port_range(self):
        """PORT_HOP_RANGE 只写一个数字时也要能比。"""
        self.assertIn("hy2_hi\" = \"$hy2_lo", self.body)



class PortOwnerParseTests(unittest.TestCase):
    """从 ss 输出抠进程名的管道不能因无匹配而炸掉 set -e。

    真机 bug：面板改端口提示"成功"，实际什么都没改。
    根因是 port_owner 的取值管道用了永远匹配不上的 grep 正则 ——
    ss 的输出行尾有大量空白且以 )) 收尾 → grep 返回 1 →
    pipefail 让整条管道返回 1 → 裸赋值触发 set -e → 静默退出。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = CONFIG.read_text(encoding="utf-8")

if __name__ == "__main__":
    unittest.main()