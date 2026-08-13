import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_audit_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


class TrafficDeltaTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()

    def test_collect_does_not_clear_hysteria_counters(self):
        source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertNotIn('/traffic?clear=1', source)
        self.assertIn('hysteria_api("/traffic"', source)

    def test_repeated_snapshots_are_not_double_counted(self):
        state = {
            "month_tx": 0,
            "month_rx": 0,
            "lifetime_tx": 0,
            "lifetime_rx": 0,
        }
        self.ns["accumulate_user_traffic"](state, {"tx": 100, "rx": 250})
        self.ns["accumulate_user_traffic"](state, {"tx": 100, "rx": 250})
        self.assertEqual(100, state["month_tx"])
        self.assertEqual(250, state["month_rx"])
        self.ns["accumulate_user_traffic"](state, {"tx": 140, "rx": 300})
        self.assertEqual(140, state["month_tx"])
        self.assertEqual(300, state["month_rx"])
        self.assertEqual(140, state["last_tx"])

    def test_counter_reset_counts_new_window_only(self):
        state = {"last_tx": 900, "last_rx": 800, "month_tx": 900, "month_rx": 800,
                 "lifetime_tx": 900, "lifetime_rx": 800}
        tx, rx = self.ns["accumulate_user_traffic"](state, {"tx": 10, "rx": 20})
        self.assertEqual(10, tx)
        self.assertEqual(20, rx)
        self.assertEqual(910, state["month_tx"])


class RateLimitEvictionTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()
        self.ns["RATE_BUCKETS"].clear()

    def test_idle_keys_are_evicted_when_map_grows(self):
        now = time.time()
        buckets = self.ns["RATE_BUCKETS"]
        for index in range(300):
            buckets[f"api:203.0.113.{index}"] = [now - 120]
        allowed = self.ns["rate_limit_allow"]("api", "198.51.100.9", 10, 60)
        self.assertTrue(allowed)
        self.assertLess(len(buckets), 50)
        self.assertIn("api:198.51.100.9", buckets)


class DeleteUserResidueTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.mode_file = root / "client-mode.json"
        self.state_file = root / "state.json"
        self.mode_file.write_text(
            json.dumps({"default": {"mode": "bbr"}, "users": {"bob": {"mode": "brutal", "up_mbps": 10, "down_mbps": 20}}}),
            encoding="utf-8",
        )
        self.state_file.write_text(
            json.dumps({"users": {"bob": {"month_tx": 9, "last_tx": 9}, "alice": {"month_tx": 1}}}),
            encoding="utf-8",
        )
        self.ns["MODE_FILE"] = self.mode_file
        self.ns["STATE_FILE"] = self.state_file

    def tearDown(self):
        self.temporary.cleanup()

    def test_forget_user_clears_mode_override_and_traffic_state(self):
        self.ns["forget_user_side_state"]("bob")
        modes = json.loads(self.mode_file.read_text(encoding="utf-8"))
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertNotIn("bob", modes["users"])
        self.assertNotIn("bob", state["users"])
        self.assertIn("alice", state["users"])


class InputValidationTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_backend_namespace()

    def test_nan_brutal_rates_fall_back_to_bbr(self):
        mode = self.ns["normalize_mode"](
            {"mode": "brutal", "up_mbps": float("nan"), "down_mbps": 20}
        )
        self.assertEqual("bbr", mode["mode"])

    def test_invalid_backup_retention_defaults_and_clamps(self):
        self.ns["load_env"] = lambda: {"BACKUP_RETENTION_DAYS": "nope"}
        self.assertEqual(14, self.ns["backup_retention_days"]())
        self.ns["load_env"] = lambda: {"BACKUP_RETENTION_DAYS": "-3"}
        self.assertEqual(1, self.ns["backup_retention_days"]())
        self.ns["load_env"] = lambda: {"BACKUP_RETENTION_DAYS": "99999"}
        self.assertEqual(3650, self.ns["backup_retention_days"]())


@unittest.skipIf(os.name == "nt", "swap harness needs Linux paths; run via WSL")
class SwapfileSafetyTests(unittest.TestCase):
    def test_failed_swapon_does_not_write_fstab(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fstab = root / "fstab"
            fstab.write_text("# empty\n", encoding="utf-8")
            swapfile = root / "swapfile"
            trace = root / "trace.log"
            result = self._run(root, fstab, swapfile, trace, swapon_ok=False, mem_kb=512000)
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertNotIn("/swapfile none swap", fstab.read_text(encoding="utf-8"))
            self.assertIn("未写入", result.stderr + result.stdout)

    def test_successful_swapon_writes_fstab_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fstab = root / "fstab"
            fstab.write_text("# empty\n", encoding="utf-8")
            swapfile = root / "swapfile"
            trace = root / "trace.log"
            result = self._run(root, fstab, swapfile, trace, swapon_ok=True, mem_kb=512000)
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertEqual(1, fstab.read_text(encoding="utf-8").count("/swapfile none swap"))

    def _run(self, root, fstab, swapfile, trace, *, swapon_ok, mem_kb):
        import shlex
        import subprocess

        source = (ROOT / "lib/install.sh").read_text(encoding="utf-8")
        patched = root / "install.sh"
        patched.write_text(
            source.replace("/swapfile", swapfile.as_posix())
            .replace("/etc/fstab", fstab.as_posix())
            .replace("/proc/meminfo", (root / "meminfo").as_posix())
            .replace("/proc/swaps", (root / "swaps").as_posix()),
            encoding="utf-8",
        )
        (root / "meminfo").write_text(f"MemTotal:        {mem_kb} kB\n", encoding="utf-8")
        (root / "swaps").write_text("Filename\tType\tSize\tUsed\tPriority\n", encoding="utf-8")
        commands = root / "commands"
        commands.mkdir()
        for name, body in {
            "swapon": (
                f'printf "swapon %s\\n" "$*" >> {shlex.quote(str(trace))}\n'
                'if [ "${1:-}" = "--show" ]; then exit 0; fi\n'
                + ("exit 0\n" if swapon_ok else "exit 1\n")
            ),
            "mkswap": f'printf "mkswap %s\\n" "$*" >> {shlex.quote(str(trace))}\nexit 0\n',
            "fallocate": f'printf "fallocate %s\\n" "$*" >> {shlex.quote(str(trace))}\ntouch {shlex.quote(str(swapfile))}\n',
            "dd": "exit 1\n",
            "df": 'printf "Filesystem 1B-blocks Used Available Use%% Mounted\\n/dev/sda 2000000000 1 1500000000 1 /\\n"\n',
            "modprobe": "exit 0\n",
        }.items():
            path = commands / name
            path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
            path.chmod(0o755)
        sysctl = root / "usr/sbin"
        sysctl.mkdir(parents=True)
        (sysctl / "sysctl").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (sysctl / "sysctl").chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{commands}:{sysctl}:{env['PATH']}"
        return subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -Eeuo pipefail
source {shlex.quote(str(patched))}
log() {{ :; }}
warn() {{ printf 'WARN: %s\\n' "$*" >&2; }}
ensure_low_memory_swap
""",
            ],
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
