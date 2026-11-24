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
        self.assertEqual(m.group(1), "1.8.3")

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
        self.assertIn('local full_version="$SCRIPT_VERSION"', self.backup)
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
        """有 FETCH_COMMIT → 一律拼上提交哈希(main/release 轨道)。

        新语义:不以内存 AIO_VERSION 做判据(read_env 会把 config.env
        旧值载入,导致哈希永远拼不上、版本卡死),直接
        SCRIPT_VERSION.<commit7>。
        """
        self.assertIn('full_version="$SCRIPT_VERSION.${HY2_FETCH_COMMIT:0:7}"', self.backup)

    def test_repair_prefers_fetch_commit_over_stale_env(self):
        """repair 必须以本次拉取的提交为准,不能被 config.env 旧值带偏。

        真实事故:read_env 把 config.env 里上次写的 1.7.3.4f40b4e 载入内存,
        它永远≠SCRIPT_VERSION → FETCH_COMMIT 永远拼不上 → 版本卡死旧提交。
        修后:有 FETCH_COMMIT 一律 SCRIPT_VERSION.<commit7>;
        无 FETCH_COMMIT(本地直装)才退回 core.sh 构建版本。
        """
        self.assertIn('local full_version="$SCRIPT_VERSION"', self.backup)
        self.assertIn('full_version="$SCRIPT_VERSION.${HY2_FETCH_COMMIT:0:7}"', self.backup)
        # 兜底分支:仅在拿不到 FETCH_COMMIT 时用 AIO_VERSION
        self.assertIn('full_version="$AIO_VERSION"', self.backup)
        self.assertIn('!= "$SCRIPT_VERSION"', self.backup)

    def test_never_writes_bare_base_version(self):
        """任何情况下都不能把纯基础号写进 config.env(那正是"固定"的根因)。"""
        self.assertNotIn('"$ENV_FILE" "$SCRIPT_VERSION"', self.backup)

    def test_full_version_never_empty(self):
        """跨基础号升级时 full_version 不允许为空写进 env。

        兜底顺序:FETCH_COMMIT → AIO_VERSION(core.sh 构建版本) → SCRIPT_VERSION。
        """
        self.assertIn('elif [ -n "$AIO_VERSION" ]', self.backup)
