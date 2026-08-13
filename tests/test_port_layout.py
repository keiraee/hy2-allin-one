import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str):
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class PortLayoutTests(unittest.TestCase):
    def test_rejects_every_internal_tcp_port_collision(self):
        result = run_bash(
            """
source lib/core.sh
port_layout_is_valid 443 9999
! port_layout_is_valid 443 443
! port_layout_is_valid 18081 9999
! port_layout_is_valid 443 18081
! port_layout_is_valid invalid 9999
! port_layout_is_valid 443 invalid
"""
        )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_same_numeric_udp_and_tcp_ports_are_allowed(self):
        result = run_bash(
            """
source lib/core.sh
HY2_PORT=443
port_layout_is_valid 443 9999
"""
        )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    @unittest.skipIf(os.name == "nt", "native Linux paths required for config fixture")
    def test_read_env_rejects_a_conflicting_or_invalid_stats_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / "config.env"
            env_file.write_text("PANEL_PORT=443\nSTATS_PORT=443\n", encoding="utf-8")
            conflict = run_bash(
                f"source lib/core.sh; ENV_FILE={str(env_file)!r}; read_env"
            )
            env_file.write_text(
                "PANEL_PORT=443\nSTATS_PORT=not-a-port\n", encoding="utf-8"
            )
            invalid = run_bash(
                f"source lib/core.sh; ENV_FILE={str(env_file)!r}; read_env"
            )

        self.assertNotEqual(0, conflict.returncode)
        self.assertIn("冲突", conflict.stderr)
        self.assertNotEqual(0, invalid.returncode)
        self.assertIn("统计端口", invalid.stderr)

    def test_install_checks_layout_and_all_runtime_port_occupancy(self):
        install = (ROOT / "hy2.sh").read_text(encoding="utf-8")
        layout_check = 'validate_port_layout "$PANEL_PORT" "$STATS_PORT"'
        occupancy_check = (
            'ensure_install_ports_available "$HY2_PORT" "$PANEL_PORT" "$STATS_PORT"'
        )
        write_env = 'cat > "$ENV_FILE"'

        self.assertIn(layout_check, install)
        self.assertIn(occupancy_check, install)
        self.assertLess(install.index(layout_check), install.index(write_env))
        self.assertLess(install.index(occupancy_check), install.index(write_env))

    @unittest.skipIf(os.name == "nt", "native Linux shell required for port stubs")
    def test_install_rejects_occupied_udp_and_each_tcp_listener(self):
        available = run_bash(
            """
source lib/core.sh
port_is_used() { return 1; }
tcp_port_is_used() { return 1; }
ensure_install_ports_available 8443 443 9999
"""
        )
        self.assertEqual(0, available.returncode, available.stderr or available.stdout)

        scenarios = (
            ("port_is_used() { [ \"$1\" = 8443 ]; }\ntcp_port_is_used() { return 1; }", "代理 UDP"),
            ("port_is_used() { return 1; }\ntcp_port_is_used() { [ \"$1\" = 443 ]; }", "面板 TCP"),
            ("port_is_used() { return 1; }\ntcp_port_is_used() { [ \"$1\" = 9999 ]; }", "统计 TCP"),
            ("port_is_used() { return 1; }\ntcp_port_is_used() { [ \"$1\" = 18081 ]; }", "内部后端 TCP"),
        )
        for stubs, message in scenarios:
            with self.subTest(message=message):
                blocked = run_bash(
                    f"source lib/core.sh\n{stubs}\nensure_install_ports_available 8443 443 9999"
                )
                self.assertNotEqual(0, blocked.returncode)
                self.assertIn(message, blocked.stderr)

    @unittest.skipIf(os.name == "nt", "native Linux network namespace required")
    def test_real_udp_and_tcp_listeners_are_detected(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket, socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        ) as tcp_socket:
            udp_socket.bind(("127.0.0.1", 0))
            tcp_socket.bind(("127.0.0.1", 0))
            tcp_socket.listen(1)
            udp_port = udp_socket.getsockname()[1]
            tcp_port = tcp_socket.getsockname()[1]

            result = run_bash(
                f"source lib/core.sh\nport_is_used {udp_port}\ntcp_port_is_used {tcp_port}"
            )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_status_uses_configured_panel_and_stats_ports(self):
        result = run_bash(
            r"""
source lib/core.sh
source lib/cli.sh
need_root() { :; }
read_env() {
  AIO_VERSION=test
  DOMAIN=panel.example.com
  PANEL_PATH=admin
  PANEL_PORT=18443
  STATS_PORT=19999
  HY2_PORT=28443
}
obfs_is_enabled() { return 1; }
systemctl() { :; }
ss() {
  printf '%s\n' \
    'tcp LISTEN 0 128 127.0.0.1:80' \
    'tcp LISTEN 0 128 127.0.0.1:443' \
    'tcp LISTEN 0 128 127.0.0.1:9999' \
    'tcp LISTEN 0 128 127.0.0.1:18443' \
    'tcp LISTEN 0 128 127.0.0.1:19999' \
    'tcp LISTEN 0 128 127.0.0.1:18081' \
    'udp UNCONN 0 0 0.0.0.0:28443'
}
status_cmd
"""
        )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        listening = [line for line in result.stdout.splitlines() if "LISTEN" in line or "UNCONN" in line]
        rendered = "\n".join(listening)
        for port in (18443, 19999, 18081, 28443):
            self.assertIn(f":{port}", rendered)
        for stale in (80, 443, 9999):
            self.assertNotIn(f":{stale}", rendered)


if __name__ == "__main__":
    unittest.main()
