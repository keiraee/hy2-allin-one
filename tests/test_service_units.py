import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    # Windows 下 bash -c 传参会弄坏双引号，落盘执行与 test_upgrade_source 一致。
    path = ROOT / "tests" / f".tmp_units_{os.getpid()}.sh"
    path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
    try:
        return subprocess.run(
            ["bash", path.relative_to(ROOT).as_posix()],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)


# getent_rc=0 模拟 systemd-journal 组存在；1 模拟缺失。
GENERATE_TEMPLATE = """
set -Eeuo pipefail
source lib/core.sh
source lib/config.sh
base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT
SERVICE_FILE="$base/hy2-aio.service"
RELOAD_PATH_FILE="$base/reload-hysteria.path"
RELOAD_SERVICE_FILE="$base/reload-hysteria.service"
HYSTERIA_CONTROL_FILE="$base/hysteria-control.sh"
HYSTERIA_DROPIN_DIR="$base/dropin"
HYSTERIA_DROPIN_FILE="$base/dropin/hy2-switch.conf"
XRAY_SERVICE_FILE="$base/hy2-xray.service"
XRAY_PRESTART_FILE="$base/xray-prestart.sh"
XRAY_RELOAD_PATH_FILE="$base/reload-xray.path"
XRAY_RELOAD_SERVICE_FILE="$base/reload-xray.service"
XRAY_CONTROL_FILE="$base/xray-control.sh"
APP_DIR="$base/app"
getent() { return %d; }
write_systemd
cat "$SERVICE_FILE"
"""


class Hy2AioUnitTests(unittest.TestCase):
    def generate(self, getent_rc: int) -> str:
        result = run_bash(GENERATE_TEMPLATE % getent_rc)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return result.stdout

    def test_journal_group_included_when_present(self):
        unit = self.generate(0)
        self.assertIn("SupplementaryGroups=hysteria caddy systemd-journal", unit)

    def test_journal_group_omitted_when_missing(self):
        # 没有 systemd-journal 组的系统上写死该组，hy2-aio 可能直接起不来；
        # 缺组时应只给 hysteria caddy，日志解析/导出降级但服务必须能启动。
        unit = self.generate(1)
        self.assertIn("SupplementaryGroups=hysteria caddy", unit)
        self.assertNotIn("systemd-journal", unit)


if __name__ == "__main__":
    unittest.main()
