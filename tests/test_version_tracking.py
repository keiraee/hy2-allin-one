"""版本号必须随提交推进,不能"固定"。

小k 反馈:面板版本一直显示 v1.7.3,改了几十版都不变。
根因两层:
1. core.sh 里 SCRIPT_VERSION="1.7.3" 手写死,无人 bump(当时已 68 提交未动)
2. repair_cmd(upgrade 落盘路径)写 config.env 用的是 SCRIPT_VERSION 纯基础号

修法:
- core.sh: git 环境下 AIO_VERSION = 基础号.提交数.g短哈希(构建时注入)
- backup.sh: repair 写 config.env 改用 AIO_VERSION;无 git 时用 HY2_FETCH_COMMIT 兜底
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "lib" / "core.sh"
BACKUP = ROOT / "lib" / "backup.sh"


class VersionTrackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CORE.read_text(encoding="utf-8")
        cls.backup = BACKUP.read_text(encoding="utf-8")

    def test_base_version_is_semver_constant(self):
        """基础版本号仍是一个语义化常量,发布大版本手动 bump。"""
        m = re.search(r'SCRIPT_VERSION="(\d+\.\d+\.\d+)"', self.core)
        self.assertIsNotNone(m, "SCRIPT_VERSION 基础号丢失")
        self.assertEqual(m.group(1), "1.7.3")

    def test_git_build_info_injected(self):
        """AIO_VERSION 必须拼上提交数与短哈希(构建时注入)。"""
        self.assertIn("rev-list --count HEAD", self.core)
        self.assertIn("rev-parse --short", self.core)
        self.assertIn("g$SCRIPT_COMMIT", self.core)

    def test_non_git_fallback(self):
        """非 git 环境(安装后的 modules)退回基础版本,不报错。"""
        self.assertIn('AIO_VERSION="$SCRIPT_VERSION"', self.core)

    def test_repair_writes_full_version(self):
        """repair_cmd(upgrade 落盘路径)必须写完整版本,不是纯基础号。"""
        self.assertIn('local full_version="${AIO_VERSION:-$SCRIPT_VERSION}"', self.backup)
        self.assertIn('"$ENV_FILE" "$full_version"', self.backup)
        # 不再直接把 SCRIPT_VERSION 传给 python 写 env
        self.assertNotIn(
            '"$ENV_FILE" "$SCRIPT_VERSION"',
            self.backup,
            "repair 仍把纯基础版本号写入 config.env",
        )

    def test_repair_falls_back_to_fetch_commit(self):
        """无 git 时用 HY2_FETCH_COMMIT 兜底拼版本。"""
        self.assertIn("HY2_FETCH_COMMIT:0:7", self.backup)

    def test_backend_reads_env_version(self):
        """后端/面板读的是 config.env 的 AIO_VERSION(链路不变,哨兵)。"""
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn('env.get("AIO_VERSION"', backend)


if __name__ == "__main__":
    unittest.main()


class VersionTrackSemanticsTests(unittest.TestCase):
    """三条轨道的版本语义(小k 质疑后推演清楚,写死防回归)。

    main 轨道:  modules=tarball 无 .git → core.sh git 探测失效 →
                AIO_VERSION=纯基础号 → repair 拼 FETCH_COMMIT →
                main 每推一版,upgrade 后版本就变。
    release 轨道: tag tarball 里 SCRIPT_VERSION 已 bump → 同走 FETCH_COMMIT
                → 1.8.0.<taghash>。
    开发机:      git checkout → AIO_VERSION 已带构建号 → 原样保留,
                不被 FETCH_COMMIT 二次拼接。
    """

    @classmethod
    def setUpClass(cls):
        cls.backup = BACKUP.read_text(encoding="utf-8")

    def test_tarball_mode_appends_fetch_commit(self):
        """纯基础号 + 有 FETCH_COMMIT → 拼上提交哈希(main/release 轨道)。"""
        self.assertIn('[ "$full_version" = "$SCRIPT_VERSION" ]', self.backup)
        self.assertIn('$SCRIPT_VERSION.${HY2_FETCH_COMMIT:0:7}', self.backup)

    def test_dev_checkout_keeps_build_version(self):
        """git checkout 的 AIO_VERSION(带 .N.gHASH)不被二次拼接。"""
        # 判据是 full_version==SCRIPT_VERSION 才拼,带构建号时必然不等 → 保留
        self.assertIn('local full_version="${AIO_VERSION:-$SCRIPT_VERSION}"', self.backup)

    def test_never_writes_bare_base_version(self):
        """任何情况下都不能把纯基础号写进 config.env(那正是"固定"的根因)。"""
        self.assertNotIn('"$ENV_FILE" "$SCRIPT_VERSION"', self.backup)
