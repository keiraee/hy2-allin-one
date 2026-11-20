"""订阅项展开子菜单 + 二维码导入。

小k 要的是「点击订阅项 → 展开出复制链接 / 二维码导入」。

二维码必须在浏览器端生成：目标机是 4GB 小机器，不能为了这个去装
qrcode/Pillow。所以只有一段同源 JS（assets/vendor/qrcode.min.js），
后端零改动。
"""

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "lib" / "panel.sh"
CONFIG = ROOT / "lib" / "config.sh"
VENDOR = ROOT / "assets" / "vendor" / "qrcode.min.js"


def panel_text() -> str:
    return PANEL.read_text(encoding="utf-8")


def js_block() -> str:
    t = panel_text()
    marker = chr(10) + "<script>" + chr(10)
    start = t.index(marker, t.index("<<'HTML'")) + len(marker)
    end = t.index("</script>", start)
    return t[start:end]


class CspAllowsImagesTests(unittest.TestCase):
    """CSP 的 img-src 必须是 'self' data:。

    原来写的是 img-src 'none'，图标和二维码全被浏览器拦掉。
    本地预览起的是普通 http.server（没有 CSP 头），所以这个 bug
    在开发时完全看不出来 —— 上真机才发现图标根本没显示。
    """

    @classmethod
    def setUpClass(cls):
        cls.cfg = CONFIG.read_text(encoding="utf-8")

    def test_script_src_allows_self(self):
        """script-src 必须带 'self'，否则同源 <script src> 被拦。

        这条是真机踩出来的：img-src 修好之后二维码仍然显示「库没装好」，
        因为 script-src 只有 'unsafe-inline' —— 内联脚本能跑，但
        vendor/qrcode.min.js 这种同源外部脚本会被 CSP 直接拒绝。
        qrcode 变量因此一直是 undefined，openQr 走 fallback 分支。
        """
        self.assertIn("script-src 'self'", self.cfg)

    def test_img_src_not_none(self):
        self.assertNotIn("img-src 'none'", self.cfg)

    def test_img_src_allows_self(self):
        self.assertIn("img-src 'self'", self.cfg)

    def test_img_src_allows_data_uri(self):
        """canvas.toDataURL 和未来的内联小图都靠 data:。"""
        self.assertIn("data:", self.cfg)

    def test_still_blocks_third_party(self):
        """放宽到 self 即可，不能变成 *。"""
        self.assertNotIn("img-src *", self.cfg)


class QrLibraryTests(unittest.TestCase):
    def test_vendor_file_present(self):
        self.assertTrue(VENDOR.is_file(), "缺 assets/vendor/qrcode.min.js")

    def test_reasonable_size(self):
        size = VENDOR.stat().st_size
        self.assertLess(size, 40_000, f"{size} 字节偏大，会拖慢面板首屏")
        self.assertGreater(size, 5_000, "文件太小，可能下载不全")

    def test_has_no_sourcemap_comment(self):
        """留着它浏览器会去请求不存在的 .map，控制台一条红。"""
        text = VENDOR.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("sourceMappingURL", text)

    def test_defines_qrcode(self):
        text = VENDOR.read_text(encoding="utf-8", errors="replace")
        self.assertIn("qrcode", text)

    def test_hash_pinned_in_panel(self):
        want = hashlib.sha256(VENDOR.read_bytes()).hexdigest()
        self.assertIn(want, panel_text(), "PANEL_VENDOR_FILES 里的哈希与实际不符")

    def test_loaded_same_origin(self):
        """必须同源：CSP script-src 只允许 self 和 inline，外域会被拦。"""
        self.assertIn('<script src="vendor/qrcode.min.js"></script>', panel_text())

    def test_not_from_cdn(self):
        text = panel_text()
        for host in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
            self.assertNotIn(host, text)


class VendorInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = PANEL.read_text(encoding="utf-8")
        start = src.index("install_panel_vendor()")
        cls.body = src[start : start + 2200]
        cls.src = src

    def test_vendor_dir_under_web_root(self):
        self.assertIn('PANEL_VENDOR_DIR="${WEB_DIR}/vendor"', self.src)

    def test_verifies_sha256(self):
        self.assertIn("font_sha256", self.body)

    def test_failure_is_non_fatal(self):
        self.assertIn("return 0", self.body)

    def test_called_from_write_panel(self):
        body = self.src[self.src.index("write_panel()"):]
        self.assertIn("install_panel_vendor || true", body)


class ExpandableMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = panel_text()

    def test_helpers_defined(self):
        for fn in ("menuItemExpandable", "menuSubItem", "subMenu"):
            self.assertIn(f"function {fn}(", self.src)

    def test_sub_menu_has_two_actions(self):
        body = self.src[self.src.index("function subMenu("):]
        body = body[: body.index("\n}\n")]
        self.assertIn("复制链接", body)
        self.assertIn("二维码导入", body)

    def test_three_subscriptions_use_expandable(self):
        for label in ("Clash 订阅", "v2ray 订阅", "sing-box 订阅"):
            self.assertIn(f'subMenu(user.username,"{label}"', self.src)

    def test_caret_rotates_on_open(self):
        self.assertIn(".mi-group.open>.mi-head .mi-caret", self.src)

    def test_sub_hidden_by_default(self):
        self.assertIn(".mi-sub{display:none", self.src)

    def test_aria_expanded_tracked(self):
        self.assertIn('head.setAttribute("aria-expanded"', self.src)


class QrModalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = panel_text()
        cls.js = js_block()

    def test_modal_markup_present(self):
        for el_id in ("qrModal", "qrCanvas", "qrHint", "qrFallback", "qrCopy", "qrDone"):
            self.assertIn(f'id="{el_id}"', self.src)

    def test_openQr_fetches_url_from_backend(self):
        """不接受前端自己拼 URL：token 由后端给，避免拼错 panel_path / fmt。"""
        body = self.js[self.js.index("async function openQr("):]
        body = body[: body.index("\n}\n")]
        self.assertIn('apiPost("api/user/credentials"', body)

    def test_draws_with_quiet_zone(self):
        body = self.js[self.js.index("function drawQr("):]
        body = body[: body.index("\n}\n")]
        self.assertIn("quiet", body)

    def test_white_background_filled(self):
        """透明底在深色主题下会和背景糊在一起，手机扫不出来。"""
        body = self.js[self.js.index("function drawQr("):]
        body = body[: body.index("\n}\n")]
        self.assertIn("#ffffff", body)

    def test_fallback_when_library_missing(self):
        body = self.js[self.js.index("async function openQr("):]
        body = body[: body.index("\n}\n")]
        self.assertIn('typeof qrcode !== "function"', body)
        self.assertIn("fallback.hidden = false", body)

    def test_canvas_scaled_for_retina(self):
        body = self.js[self.js.index("function drawQr("):]
        body = body[: body.index("\n}\n")]
        self.assertIn("scale", body)

    def test_close_clears_url(self):
        body = self.js[self.js.index("function closeQr("):]
        body = body[: body.index("\n}\n")]
        self.assertIn('qrCurrentUrl = ""', body)


class QrSyntaxGuardTests(unittest.TestCase):
    """面板 JS 必须语法正确 —— 上一版确认框里的真换行差点让页面白屏。"""

    def test_js_parses_with_node(self):
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            # WSL 里通常没装 node，但 Windows 宿主有 —— 找几个常见位置
            for cand in (
                "/mnt/c/Users/HCY520MH/AppData/Local/Programs/Alma/alma-server/runtime/node",
                "C:/Users/HCY520MH/AppData/Local/Programs/Alma/alma-server/runtime/node",
            ):
                if Path(cand).exists():
                    node = cand
                    break
        if not node:
            self.skipTest("node 不可用")
        tmp = ROOT / "tests" / ".qr_check.mjs"
        tmp.write_text(js_block(), encoding="utf-8")
        try:
            r = subprocess.run([node, "--check", str(tmp)],
                               capture_output=True, text=True, check=False)
            self.assertEqual(0, r.returncode, f"JS 语法错误：{r.stderr[:500]}")
        finally:
            tmp.unlink(missing_ok=True)


class GlyphIconTests(unittest.TestCase):
    """子菜单用的 copy / qr 两个 sprite 图标。"""

    def test_symbols_defined(self):
        text = panel_text()
        self.assertIn('id="i-copy"', text)
        self.assertIn('id="i-qr"', text)


if __name__ == "__main__":
    unittest.main()