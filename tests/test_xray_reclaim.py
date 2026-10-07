import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    path = ROOT / "tests" / f".tmp_reclaim_{os.getpid()}.sh"
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


HARNESS = r"""
set -Eeuo pipefail
source lib/core.sh
TRACE="$(mktemp)"
sleep() { :; }
tcp_listen_pids() { printf '%s\n' "${LISTEN_PIDS-}"; }
pid_cgroup() { printf '%s\n' "${CGROUP_MAP[$1]-}"; }
ps() {
  local pid=""
  for arg in "$@"; do
    case "$arg" in
      [0-9]*) pid="$arg" ;;
    esac
  done
  case " $* " in
    *" -o comm= "*)
      printf '%s\n' "${COMM_MAP[$pid]-}"
      ;;
    *)
      printf '%s\n' "${ARGS_MAP[$pid]-}"
      ;;
  esac
}
kill() { printf 'kill %s\n' "$*" >> "$TRACE"; LISTEN_PIDS=""; }
systemctl() {
  printf 'systemctl %s\n' "$*" >> "$TRACE"
  case "$*" in
    "list-unit-files --type=service --no-legend --no-pager")
      printf '%s\n' "xray.service enabled enabled" "hy2-xray.service enabled enabled"
      ;;
    "list-units --all --type=service --plain --no-legend --no-pager xray*")
      printf '%s\n' "xray.service loaded active running"
      ;;
    "is-active --quiet hy2-xray.service") return "${IS_ACTIVE_RC:-0}" ;;
    *) return 0 ;;
  esac
}
declare -A COMM_MAP ARGS_MAP CGROUP_MAP
COMM_MAP[663]=xray
ARGS_MAP[663]="/usr/local/bin/xray run -config /usr/local/etc/xray/config.json"
CGROUP_MAP[663]="0::/system.slice/xray.service"
COMM_MAP[99]=nginx
ARGS_MAP[99]="/usr/sbin/nginx"
CGROUP_MAP[99]="0::/system.slice/nginx.service"
COMM_MAP[7]=xray
ARGS_MAP[7]="/usr/local/bin/xray run -c /etc/hy2-aio/xray.json"
CGROUP_MAP[7]="0::/system.slice/hy2-xray.service"
"""

GENERATE_TEMPLATE = r"""
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
XRAY_RELOAD_PATH_FILE="$base/reload-xray.path"
XRAY_RELOAD_SERVICE_FILE="$base/reload-xray.service"
XRAY_CONTROL_FILE="$base/xray-control.sh"
XRAY_PRESTART_FILE="$base/xray-prestart.sh"
APP_DIR="$base/app"
getent() { return 0; }
write_systemd
cat "$XRAY_SERVICE_FILE"
echo "===== PRESTART ====="
cat "$XRAY_PRESTART_FILE"
"""


class XrayReclaimTests(unittest.TestCase):
    def test_disables_official_xray_unit(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=
reclaim_vless_tcp_port 443
grep -F 'systemctl disable --now xray.service' "$TRACE"
! grep -F 'disable --now hy2-xray.service' "$TRACE"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_kills_leftover_official_xray_process(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=663
reclaim_vless_tcp_port 443
grep -F 'kill 663' "$TRACE"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_skips_listener_that_exited(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=663
COMM_MAP[663]=
ARGS_MAP[663]=
reclaim_vless_tcp_port 443
! grep -q '^kill ' "$TRACE"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_dies_on_foreign_occupier(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=99
reclaim_vless_tcp_port 443
"""
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("已被占用", result.stderr)
        self.assertIn("99", result.stderr)
        self.assertNotIn("kill 99", result.stdout + result.stderr)

    def test_leaves_hy2_xray_listener_alone(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=7
reclaim_vless_tcp_port 443
! grep -q '^kill ' "$TRACE"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_pid_service_name_parses_cgroup(self):
        result = run_bash(
            HARNESS
            + r"""
pid_cgroup() {
  case "$1" in
    1) printf '%s\n' '0::/system.slice/hy2-xray.service' ;;
    2) printf '%s\n' '1:name=system.slice:system.slice/xray.service' ;;
    3) printf '%s\n' '0::/user.slice/user-0.slice/session-3.scope' ;;
    4) printf '%s\n' '0::/non-systemd' ;;
  esac
}
[ "$(pid_service_name 1)" = "hy2-xray.service" ]
[ "$(pid_service_name 2)" = "xray.service" ]
[ -z "$(pid_service_name 3)" ]
[ -z "$(pid_service_name 4)" ]
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_restart_dies_when_service_not_active(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=
IS_ACTIVE_RC=1
journalctl() { :; }
restart_hy2_xray_or_die
"""
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Xray 启动失败", result.stderr)

    def test_restart_failure_dumps_journal_and_dies(self):
        result = run_bash(
            HARNESS
            + r"""
LISTEN_PIDS=
systemctl() {
  case "$*" in
    "restart hy2-xray.service") return 1 ;;
    "is-active --quiet hy2-xray.service") return 1 ;;
    *) return 0 ;;
  esac
}
journalctl() { echo JOURNAL_DUMPED >&2; }
restart_hy2_xray_or_die
"""
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Xray 启动失败", result.stderr)
        self.assertIn("JOURNAL_DUMPED", result.stderr)

    def test_xray_unit_reclaims_port_before_start(self):
        result = run_bash(GENERATE_TEMPLATE)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        unit, script = result.stdout.split("===== PRESTART =====", 1)
        self.assertIn("ExecStartPre=+/usr/local/lib/hy2-aio/xray-prestart.sh", unit)
        self.assertIn("Conflicts=xray.service xray@.service", unit)
        self.assertIn("modules/lib/core.sh", script)
        self.assertIn("read_env", script)
        self.assertIn("reclaim_vless_tcp_port", script)

    def test_core_exposes_reclaim_on_install_and_restart_helpers(self):
        core = (ROOT / "lib" / "core.sh").read_text(encoding="utf-8")
        self.assertIn("reclaim_vless_tcp_port() {", core)
        self.assertIn("restart_hy2_xray_or_die() {", core)
        self.assertIn("disable_official_xray_units", core)
        cli = (ROOT / "lib" / "cli.sh").read_text(encoding="utf-8")
        self.assertIn("restart_hy2_xray_or_die", cli)
        backup = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8")
        self.assertIn("restart_hy2_xray_or_die", backup)


if __name__ == "__main__":
    unittest.main()
