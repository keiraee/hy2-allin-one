"""面板客户端图标（Clash / v2ray / sing-box）的生成与加载。

图标是从小k 提供的原图（512 PNG / 1024 JPG / 多尺寸 ICO）裁剪压缩来的，
不是手画 SVG。这里守住三件事：
1. 产物是合法 WebP、尺寸正确、体积够小
2. 原始素材不进 git（originals 留着方便以后重做）
3. 图标缺失时面板必须退回内置 sprite，不能白屏或留空
"""

import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"
PANEL = ROOT / "lib" / "panel.sh"


def webp_size(path: Path) -> tuple[int, int]:
    """从 WebP 头里读宽高（不解码图像）。"""
    data = path.read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", "不是 WebP"
    chunk = data[12:16]
    if chunk == b"VP8X":
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        return w, h
    if chunk == b"VP8 ":
        # VP8 关键帧：起始码后两个 16 位（14 位有效）
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return w, h
    if chunk == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return w, h
    raise AssertionError(f"未知 WebP chunk: {chunk}")


class IconAssetTests(unittest.TestCase):
    EXPECTED = {
        "clash-32.webp": (32, 32),
        "clash-64.webp": (64, 64),
        "v2ray-32.webp": (32, 32),
        "v2ray-64.webp": (64, 64),
        "singbox-32.webp": (32, 32),
        "singbox-64.webp": (64, 64),
    }

    def test_all_icons_present(self):
        for name in self.EXPECTED:
            self.assertTrue((ICON_DIR / name).is_file(), f"缺文件：{name}")

    def test_magic_and_dimensions(self):
        for name, (w, h) in self.EXPECTED.items():
            with self.subTest(name=name):
                self.assertEqual((w, h), webp_size(ICON_DIR / name))

    def test_total_size_is_small(self):
        """菜单里只有 15px，图标不该超过 20KB 总量。"""
        total = sum((ICON_DIR / n).stat().st_size for n in self.EXPECTED)
        self.assertLess(total, 20_000, f"图标总量 {total} 字节，偏大")

    def test_32_and_64_pair_exist(self):
        """Retina 需要 2x；只给一个尺寸高分屏会糊。"""
        for base in ("clash", "v2ray", "singbox"):
            self.assertTrue((ICON_DIR / f"{base}-32.webp").is_file())
            self.assertTrue((ICON_DIR / f"{base}-64.webp").is_file())


class IconNotInChecksumTests(unittest.TestCase):
    def test_not_listed_in_sha256sums(self):
        """SHA256SUMS 只登记 shell 模块，混入二进制会打破既有约定。"""
        sums = (ROOT / "SHA256SUMS").read_text(encoding="utf-8")
        self.assertNotIn("webp", sums)

    def test_gitattributes_marks_binary(self):
        """webp 必须标 binary，否则 checkout 会做换行转换写坏文件。"""
        attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.webp binary", attrs)


class PanelIconInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")
        start = cls.src.index("install_panel_icons()")
        cls.body = cls.src[start : start + 2600]

    def test_icon_dir_under_web_root(self):
        self.assertIn('PANEL_ICON_DIR="${WEB_DIR}/icons"', self.src)

    def test_has_sha256_manifest(self):
        """图标是二进制，不能靠 SHA256SUMS，这里内嵌哈希。"""
        self.assertIn("PANEL_ICON_FILES", self.src)
        import hashlib
        for name in ("clash-64.webp", "singbox-32.webp"):
            want = hashlib.sha256((ICON_DIR / name).read_bytes()).hexdigest()
            self.assertIn(want, self.src, f"{name} 的哈希没写进 PANEL_ICON_FILES")

    def test_verifies_webp_magic(self):
        self.assertIn("RIFF", self.body)

    def test_failure_is_non_fatal(self):
        """装不上图标不能让 install/repair 挂掉。"""
        self.assertIn("return 0", self.body)

    def test_called_from_write_panel(self):
        body = self.src[self.src.index("write_panel()"):]
        self.assertIn("install_panel_icons || true", body)


class ClientIconFallbackTests(unittest.TestCase):
    """图标加载失败要退回内置 sprite，不能留空白。"""

    @classmethod
    def setUpClass(cls):
        cls.src = PANEL.read_text(encoding="utf-8")
        start = cls.src.index("function clientIcon(")
        cls.body = cls.src[start : start + 900]

    def test_uses_webp_with_srcset(self):
        self.assertIn("-32.webp", self.body)
        self.assertIn("-64.webp", self.body)
        self.assertIn("srcset", self.body)

    def test_onerror_falls_back_to_svg(self):
        self.assertIn("onerror", self.body)
        self.assertIn("iconSvg(name)", self.body)

    def test_only_subscription_items_use_raster_icons(self):
        """其余菜单项（改备注等）仍用 sprite，不该去请求图标文件。"""
        self.assertIn("SUB_ICONS", self.src)
        self.assertIn('new Set(["clash","v2ray","singbox"])', self.src)

    def test_css_keeps_icon_opacity(self):
        """.ico 默认 opacity:.75 会把彩色图标压灰，img 要单独恢复。"""
        self.assertIn("img.client-ico{opacity:1", self.src)

    def test_menu_buttons_are_flex(self):
        """图标和文字并排，不用 flex 会换行。"""
        body = self.src[self.src.index(".menu button{"):]
        self.assertIn("display:flex", body[:200])


class BootstrapDownloadTests(unittest.TestCase):
    """hy2.sh 要能把图标一起拉下来，且按扩展名验证魔数。"""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "hy2.sh").read_text(encoding="utf-8")

    def test_icons_in_assets_list(self):
        for name in ("clash-32.webp", "v2ray-64.webp", "singbox-32.webp"):
            self.assertIn(f"assets/icons/{name}", self.src)

    def test_magic_chosen_by_extension(self):
        self.assertIn("*.woff2) magic='wOF2'", self.src)
        self.assertIn("*.webp)  magic='RIFF'", self.src)

    def test_download_failure_only_warns(self):
        """字体/图标下载失败只记日志，不能用 _bootstrap_die 中断升级。"""
        body = self.src[self.src.index("mkdir -p \"${target_dir}/assets/fonts\""):]
        seg = body[: body.index("rm -f \"$sums\"")]
        self.assertIn("跳过", seg)
        self.assertNotIn("_bootstrap_die", seg)


if __name__ == "__main__":
    unittest.main()