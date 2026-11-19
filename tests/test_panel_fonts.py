import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "lib" / "panel.sh"
FONT_DIR = ROOT / "assets" / "fonts"


def panel_source() -> str:
    return PANEL.read_text(encoding="utf-8")


def panel_html() -> str:
    """抽出写进 index.html 的那段 HTML。"""
    src = panel_source()
    marker = "<<'HTML'\n"
    start = src.index(marker) + len(marker)
    end = src.index("\nHTML\n", start)
    return src[start:end]


class FontAssetsTests(unittest.TestCase):
    """字体是要随仓库分发的二进制，必须真的在库里、且不是半截文件。"""

    EXPECTED = {
        "inter-400.woff2": "dd05e326cf8eac3b55acecf29c842ed73e6e6dd06491cf47f7e8800680ab3e33",
        "inter-600.woff2": "62553d159189834af73c9a6264704be5b2bee9a08da66a14768d8e5c6ffd2cdb",
        "jetbrains-mono-400.woff2": "7c53386f55c866c1b4c9309c4bcf74eda10896aab3a1780b0af5cc4976e27a27",
        "jetbrains-mono-700.woff2": "ed8b8f71b22bf3b6e1ec1cf9b24dd999785aae33d6256950c1f86c97e423b6ef",
    }

    def test_font_files_present_with_expected_hashes(self):
        for name, want in self.EXPECTED.items():
            path = FONT_DIR / name
            self.assertTrue(path.is_file(), f"缺少字体文件 {name}")
            got = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(want, got, name)

    def test_font_files_are_woff2(self):
        """WOFF2 文件头必须是 wOF2，防止下载到 HTML 错误页。"""
        for name in self.EXPECTED:
            header = (FONT_DIR / name).read_bytes()[:4]
            self.assertEqual(b"wOF2", header, name)

    def test_total_size_stays_small(self):
        """小机器部署，字体总量必须控制在 150KB 内（实际约 91KB）。"""
        total = sum((FONT_DIR / n).stat().st_size for n in self.EXPECTED)
        self.assertLess(total, 150 * 1024, f"字体总量 {total} 字节过大")
        self.assertGreater(total, 50 * 1024, "字体总量异常偏小，可能文件不全")

    def test_hashes_in_panel_match_assets(self):
        """panel.sh 里写死的哈希必须和仓库里的实际文件一致，
        否则 install_panel_fonts 会因为「校验不符」永远装不上。"""
        src = panel_source()
        table = src[src.index("PANEL_FONT_FILES=(") : src.index("\n)", src.index("PANEL_FONT_FILES=("))]
        entries = re.findall(r'"([^"]+\.woff2)\|([0-9a-f]{64})"', table)
        self.assertEqual(len(entries), len(self.EXPECTED))
        for name, want in entries:
            self.assertIn(name, self.EXPECTED)
            self.assertEqual(self.EXPECTED[name], want, name)


class FontFaceTests(unittest.TestCase):
    """@font-face 必须自托管、同源、并且带 font-display:swap。"""

    def test_four_font_faces_declared(self):
        faces = re.findall(r"@font-face\{[^}]*\}", panel_html())
        self.assertEqual(4, len(faces), faces)
        families = {re.search(r'font-family:"([^"]+)"', f).group(1) for f in faces}
        self.assertEqual({"Inter", "JetBrains Mono"}, families)

    def test_sources_are_local_relative_paths(self):
        """CSP 是 default-src 'self'，任何跨域字体都会被浏览器拦掉。
        所以 src 只能是同源的相对路径。"""
        faces = re.findall(r"@font-face\{[^}]*\}", panel_html())
        for face in faces:
            url = re.search(r'src:url\("([^"]+)"\)', face).group(1)
            self.assertFalse(url.startswith("http"), f"字体不能跨域加载：{url}")
            self.assertTrue(url.startswith("fonts/"), f"字体必须走同源相对路径：{url}")
            self.assertTrue(url.endswith(".woff2"), url)

    def test_font_display_is_swap(self):
        """小机器首次打开不该白屏等字体，先渲染再替换。"""
        faces = re.findall(r"@font-face\{[^}]*\}", panel_html())
        for face in faces:
            self.assertIn("font-display:swap", face)

    def test_referenced_files_actually_exist(self):
        faces = re.findall(r"@font-face\{[^}]*\}", panel_html())
        for face in faces:
            name = re.search(r'src:url\("fonts/([^"]+)"\)', face).group(1)
            self.assertTrue((FONT_DIR / name).is_file(), f"HTML 引用了不存在的字体 {name}")


class FontStackTests(unittest.TestCase):
    """字体栈顺序决定一切，这里把关键约定钉住。"""

    def test_body_stack_puts_inter_first(self):
        m = re.search(r"--font:([^;]+);", panel_html())
        self.assertIsNotNone(m)
        stack = m.group(1)
        self.assertTrue(stack.strip().startswith("Inter,"), stack)

    def test_chinese_fallbacks_after_webfont(self):
        """latin 子集不含汉字，中文必须靠系统字体回退；
        顺序错了中文会掉进 serif 或者出现豆腐块。"""
        m = re.search(r"--font:([^;]+);", panel_html())
        stack = m.group(1)
        for cjk in ("PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC"):
            self.assertIn(cjk, stack, f"中文回退缺少 {cjk}")
        self.assertLess(stack.index("Inter"), stack.index("PingFang SC"))

    def test_mono_stack_puts_jetbrains_first(self):
        m = re.search(r"--mono:([^;]+);", panel_html())
        self.assertIsNotNone(m)
        self.assertIn('"JetBrains Mono"', m.group(1))
        self.assertLess(m.group(1).index("JetBrains Mono"), m.group(1).index("Consolas"))

    def test_does_not_reference_third_party_cdn(self):
        """面板不能引 Google Fonts / jsdelivr：国内不可达，且破坏 CSP。"""
        html = panel_html()
        for bad in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"):
            self.assertNotIn(bad, html, f"不应出现第三方字体 CDN：{bad}")


class FontInstallTests(unittest.TestCase):
    """安装逻辑必须「可选且幂等」：失败不能拖垮 install，已装不重复下载。"""

    @classmethod
    def setUpClass(cls):
        cls.src = panel_source()

    def test_failure_does_not_abort_install(self):
        block = self.src[self.src.index("install_panel_fonts()") :]
        block = block[: block.index("\nwrite_panel()")]
        # 整个函数里不应出现 die
        self.assertNotIn("die ", block, "字体安装失败不能 die，只能 warn")

    def test_skips_download_when_already_present(self):
        block = self.src[self.src.index("install_panel_fonts()") :]
        block = block[: block.index("\nwrite_panel()")]
        self.assertIn("force", block)
        self.assertIn('[ "${#missing[@]}" -eq 0 ] && return 0', block)

    def test_call_site_is_guarded(self):
        self.assertIn("install_panel_fonts || true", self.src)

    def test_runs_after_html_is_written(self):
        """字体要放在 HTML 之后：字体挂了面板也得是能用的。"""
        html_write = self.src.index('cat > "$WEB_DIR/index.html"')
        font_call = self.src.rindex("install_panel_fonts || true")
        self.assertGreater(font_call, html_write)


class FontDeliveryTests(unittest.TestCase):
    """字体要能被下发到新机器，缺了下发链路就等于只有仓库有。"""

    @classmethod
    def setUpClass(cls):
        cls.boot = (ROOT / "hy2.sh").read_text(encoding="utf-8")

    def test_fetch_modules_downloads_fonts(self):
        block = self.boot[self.boot.index("fetch_modules()") :]
        block = block[: block.index("\n# 加载本地模块")]
        for name in FontAssetsTests.EXPECTED:
            self.assertIn(name, block, f"fetch_modules 未下发 {name}")

    def test_font_download_failure_is_not_fatal(self):
        block = self.boot[self.boot.index("fetch_modules()") :]
        block = block[: block.index("\n# 加载本地模块")]
        # 字体那段不能用 _bootstrap_die
        font_part = block[block.index("mkdir -p \"${target_dir}/assets/fonts\"") :]
        self.assertNotIn("_bootstrap_die", font_part)

    def test_woff2_marked_binary_in_gitattributes(self):
        """仓库根是 `* text=auto eol=lf`，不显式标二进制的话，
        checkout 时换行符转换会直接写坏 woff2——字体加载不出来还很难查。"""
        attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertRegex(attrs, r"(?m)^\*\.woff2\s+binary\s*$")

    def test_fonts_not_in_sha256sums(self):
        """SHA256SUMS 只登记 shell 模块（有测试断言清单严格相等），
        二进制混进去会直接破坏那条约定。"""
        names = {
            line.split("  ", 1)[1]
            for line in (ROOT / "SHA256SUMS").read_text(encoding="ascii").splitlines()
            if line.strip()
        }
        for font in FontAssetsTests.EXPECTED:
            self.assertNotIn(font, names)
            self.assertFalse(any("assets/" in n for n in names), "assets 不该出现在 SHA256SUMS")


if __name__ == "__main__":
    unittest.main()