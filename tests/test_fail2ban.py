import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = "hy2-a1b2c3d4"
HOST_PATTERN = r"(?P<host>(?:\d{1,3}\.){3}\d{1,3}|[0-9A-Fa-f:]+)"


def generated_filter() -> str:
    source = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
    marker = 'cat > "$filter_file" <<EOF\n'
    start = source.index(marker) + len(marker)
    end = source.index("\nEOF", start)
    template = source[start:end].replace("${panel_path}", PANEL_PATH)
    rendered = subprocess.run(
        ["bash", "-s"],
        input=f"cat <<EOF\n{template}\nEOF\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if rendered.returncode:
        raise AssertionError(rendered.stderr)
    return rendered.stdout.rstrip("\n")


def filter_option(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\s*=\s*(.+)$", generated_filter(), re.MULTILINE)
    if not match:
        raise AssertionError(f"missing filter option: {name}")
    return match.group(1)


def caddy_log(
    remote_ip: str,
    *,
    method: str = "GET",
    uri: str = f"/{PANEL_PATH}/",
    status: int = 401,
    injected_header: str = "",
) -> str:
    headers = {"User-Agent": ["curl/8.0"]}
    if injected_header:
        headers["X-Test"] = [injected_header]
    entry = {
        "level": "info",
        "ts": 1786543210.125,
        "logger": "http.log.access.log0",
        "msg": "handled request",
        "request": {
            "remote_ip": remote_ip,
            "remote_port": "43110",
            "client_ip": remote_ip,
            "proto": "HTTP/2.0",
            "method": method,
            "host": "panel.example.com",
            "uri": uri,
            "headers": headers,
            "tls": {
                "resumed": False,
                "version": 772,
                "cipher_suite": 4865,
                "proto": "h2",
                "server_name": "panel.example.com",
            },
        },
        "bytes_read": 0,
        "user_id": "",
        "duration": 0.0009,
        "size": 0,
        "status": status,
        "resp_headers": {"Server": ["Caddy"]},
    }
    return json.dumps(entry, separators=(",", ":"))


def match_host(line: str):
    pattern = filter_option("failregex").replace("<HOST>", HOST_PATTERN)
    match = re.match(pattern, line)
    return match.group("host") if match else None


class Fail2BanFilterTests(unittest.TestCase):
    def test_caddy_access_log_format_is_explicitly_json(self):
        source = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        self.assertRegex(
            source,
            re.compile(
                r"log \{\{\s+output file /var/log/caddy/hy2-aio\.log \{\{.*?\}\}\s+format json",
                re.DOTALL,
            ),
        )

    def test_filter_declares_caddy_epoch_timestamp(self):
        self.assertRegex(filter_option("datepattern"), r'"ts":.*\{EPOCH\}')

    def test_matches_panel_basic_auth_failures_for_ipv4_and_ipv6(self):
        self.assertEqual("203.0.113.9", match_host(caddy_log("203.0.113.9")))
        self.assertEqual(
            "2001:db8::9",
            match_host(caddy_log("2001:db8::9", method="HEAD", uri=f"/{PANEL_PATH}/api/sync")),
        )

    def test_matches_after_fail2ban_strips_the_timestamp_prefix(self):
        line = caddy_log("203.0.113.9")
        processed = line[line.index('"logger"') :]
        self.assertEqual("203.0.113.9", match_host(processed))

    def test_does_not_match_success_or_an_unrelated_path(self):
        self.assertIsNone(match_host(caddy_log("203.0.113.9", status=200)))
        self.assertIsNone(match_host(caddy_log("203.0.113.9", uri="/subscription/token")))
        self.assertIsNone(match_host(caddy_log("203.0.113.9", uri=f"/{PANEL_PATH}-other/")))

    def test_host_is_taken_from_remote_ip_not_user_controlled_json_text(self):
        line = caddy_log(
            "198.51.100.24",
            injected_header='"remote_ip":"203.0.113.77","status":401',
        )
        self.assertEqual("198.51.100.24", match_host(line))

    def test_installer_validates_filter_and_active_jail_before_success_message(self):
        source = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        function = source[source.index("configure_fail2ban_panel()") :]
        function = function[: function.index("\n}\n", 1) + 3]
        self.assertIn("fail2ban-regex", function)
        self.assertIn("fail2ban-client status hy2-caddy-auth", function)
        self.assertNotIn("| grep", function)
        self.assertLess(
            function.index("fail2ban-client status hy2-caddy-auth"),
            function.index("fail2ban 已生效"),
        )

    @unittest.skipUnless(os.environ.get("FAIL2BAN_REGEX"), "fail2ban-regex not provided")
    def test_filter_with_official_fail2ban_parser(self):
        lines = [
            caddy_log("203.0.113.9"),
            caddy_log("2001:db8::9", method="HEAD", uri=f"/{PANEL_PATH}/api/sync"),
            caddy_log(
                "198.51.100.24",
                injected_header='"remote_ip":"203.0.113.77","status":401',
            ),
            caddy_log("192.0.2.10", status=200),
            caddy_log("192.0.2.11", uri="/subscription/token"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            filter_file = fixture / "hy2-caddy-auth.conf"
            log_file = fixture / "caddy.log"
            filter_file.write_text(generated_filter() + "\n", encoding="utf-8")
            log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            command = [os.environ["FAIL2BAN_REGEX"]]
            if os.environ.get("FAIL2BAN_REGEX_PYTHON"):
                command.insert(0, os.environ["FAIL2BAN_REGEX_PYTHON"])
            result = subprocess.run(
                [
                    *command,
                    str(log_file),
                    str(filter_file),
                    "--out",
                    "ip",
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self_check = subprocess.run(
                [
                    *command,
                    str(log_file),
                    str(filter_file),
                    "--print-all-matched",
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual(
            ["203.0.113.9", "2001:db8::9", "198.51.100.24"],
            [line.strip() for line in result.stdout.splitlines() if line.strip()],
        )
        self.assertEqual(
            0,
            self_check.returncode,
            self_check.stderr or self_check.stdout,
        )
        self.assertIn('"remote_ip":"203.0.113.9"', self_check.stdout)


if __name__ == "__main__":
    unittest.main()
