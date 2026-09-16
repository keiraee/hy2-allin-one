import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HISTORY_HEADER = [
    "时间",
    "整机接收",
    "整机发送",
    "整机合计",
    "CPU",
    "内存百分比",
    "用户",
    "在线设备",
    "用户上传",
    "用户下载",
    "用户合计",
]


def load_backend_namespace():
    shell_source = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$APP_FILE" <<\'PY\'\n'
    end_marker = '\nPY\n  chmod 0755 "$APP_FILE"'
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    namespace = {"__name__": "hy2_aio_user_traffic_test"}
    exec(compile(shell_source[start:end], "server.py", "exec"), namespace)
    return namespace


def write_history(path: Path, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(HISTORY_HEADER)
        writer.writerows(rows)


def history_row(stamp: str, username: str, upload: int, download: int) -> list[object]:
    return [
        stamp,
        0,
        0,
        0,
        0,
        0,
        username,
        0,
        upload,
        download,
        upload + download,
    ]


class UserTrafficAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.users_file = self.root / "users.json"
        self.data_file = self.root / "data.json"
        self.history = self.root / "history.csv"
        self.users_file.write_text(
            json.dumps(
                {
                    "alice": {"password": "x", "token": "t", "disabled": False},
                    "bob": {"password": "y", "token": "u", "disabled": False},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.data_file.write_text(
            json.dumps(
                {
                    "server": {"traffic": {"used": 2000}, "ip": "203.0.113.9"},
                    "users": [
                        {
                            "username": "alice",
                            "upload": 400,
                            "download": 1600,
                            "total": 2000,
                            "lifetime_total": 5000,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.namespace.update(
            {
                "USERS_FILE": self.users_file,
                "DATA_FILE": self.data_file,
                "HISTORY_CSV": self.history,
            }
        )

    def tearDown(self):
        self.temporary.cleanup()

    def analyze(self, username: str = "alice"):
        return self.namespace["user_traffic_analysis"](username)

    def test_rejects_invalid_username(self):
        with self.assertRaisesRegex(ValueError, "用户名"):
            self.analyze("bad name")

    def test_rejects_unknown_user(self):
        with self.assertRaisesRegex(ValueError, "用户不存在"):
            self.analyze("carol")

    def test_month_snapshot_without_history(self):
        payload = self.analyze()
        self.assertEqual(payload["username"], "alice")
        self.assertEqual(payload["month"]["upload"], 400)
        self.assertEqual(payload["month"]["download"], 1600)
        self.assertEqual(payload["month"]["total"], 2000)
        self.assertEqual(payload["month"]["lifetime_total"], 5000)
        self.assertEqual(payload["month"]["share_percent"], 100.0)
        self.assertEqual(payload["egress_ip"], "203.0.113.9")
        self.assertEqual(payload["series"], [])
        self.assertEqual(payload["live"], [])
        self.assertEqual(payload["sites"], [])
        self.assertEqual(payload["online"], 0)
        self.assertFalse(payload["has_history"])
        self.assertIsNone(payload["peak"])

    def test_series_uses_cumulative_deltas_and_skips_other_users(self):
        now = datetime.now(timezone.utc)
        t0 = (now - timedelta(minutes=15)).isoformat(timespec="seconds")
        t1 = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
        t2 = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
        write_history(
            self.history,
            [
                history_row(t0, "alice", 100, 200),
                history_row(t0, "bob", 900, 900),
                history_row(t1, "alice", 150, 500),
                history_row(t2, "alice", 180, 800),
            ],
        )
        payload = self.analyze()
        self.assertTrue(payload["has_history"])
        self.assertEqual(
            [(item["up"], item["down"]) for item in payload["series"]],
            [(50, 300), (30, 300)],
        )
        self.assertEqual(payload["series"][0]["t"], t1)
        self.assertEqual(payload["peak"]["t"], t1)
        self.assertEqual(payload["peak"]["total"], 350)

    def test_month_reset_does_not_create_negative_delta(self):
        now = datetime.now(timezone.utc)
        t0 = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
        t1 = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
        write_history(
            self.history,
            [
                history_row(t0, "alice", 1000, 2000),
                history_row(t1, "alice", 40, 80),
            ],
        )
        payload = self.analyze()
        self.assertEqual(payload["series"][0]["up"], 40)
        self.assertEqual(payload["series"][0]["down"], 80)

    def test_drops_samples_older_than_seven_days(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=8)).isoformat(timespec="seconds")
        recent0 = (now - timedelta(hours=3)).isoformat(timespec="seconds")
        recent1 = (now - timedelta(hours=2)).isoformat(timespec="seconds")
        write_history(
            self.history,
            [
                history_row(old, "alice", 10, 10),
                history_row(recent0, "alice", 20, 30),
                history_row(recent1, "alice", 25, 40),
            ],
        )
        payload = self.analyze()
        self.assertEqual(len(payload["series"]), 1)
        self.assertEqual(payload["series"][0]["t"], recent1)
        self.assertEqual(payload["series"][0]["up"], 5)
        self.assertEqual(payload["series"][0]["down"], 10)

    def test_reads_rotated_history_before_current_file(self):
        now = datetime.now(timezone.utc)
        t0 = (now - timedelta(minutes=20)).isoformat(timespec="seconds")
        t1 = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
        rotated = self.history.with_name("history.csv.1")
        write_history(rotated, [history_row(t0, "alice", 10, 20)])
        write_history(self.history, [history_row(t1, "alice", 40, 70)])
        payload = self.analyze()
        self.assertEqual(payload["series"][0]["up"], 30)
        self.assertEqual(payload["series"][0]["down"], 50)

    def test_zero_machine_usage_has_zero_share(self):
        self.data_file.write_text(
            json.dumps(
                {
                    "server": {"traffic": {"used": 0}},
                    "users": [
                        {
                            "username": "alice",
                            "upload": 0,
                            "download": 0,
                            "total": 0,
                            "lifetime_total": 0,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        payload = self.analyze()
        self.assertEqual(payload["month"]["share_percent"], 0.0)

    def test_handler_exposes_user_traffic_route(self):
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn('path == "/user/traffic"', backend)
        self.assertIn("user_traffic_analysis", backend)

    def test_stream_target_prefers_sniffed_hostname_and_request_ip(self):
        target = self.namespace["stream_target"](
            {
                "req_addr": "192.0.2.1:443",
                "hooked_req_addr": "www.example.com:443",
            }
        )
        self.assertEqual(target["host"], "www.example.com")
        self.assertEqual(target["ip"], "192.0.2.1")
        self.assertEqual(target["port"], "443")

    def test_stream_target_parses_ipv6(self):
        target = self.namespace["stream_target"](
            {"req_addr": "[2001:db8::1]:443", "hooked_req_addr": ""}
        )
        self.assertEqual(target["host"], "2001:db8::1")
        self.assertEqual(target["ip"], "2001:db8::1")
        self.assertEqual(target["port"], "443")

    def test_remember_user_streams_counts_deltas_and_unique_hits(self):
        state: dict = {}
        now = datetime.now(timezone.utc)
        t0 = (now - timedelta(minutes=2)).isoformat(timespec="seconds")
        t1 = now.isoformat(timespec="seconds")
        first = {
            "auth": "alice",
            "connection": 1,
            "stream": 4,
            "req_addr": "192.0.2.8:443",
            "hooked_req_addr": "cdn.example.com:443",
            "tx": 100,
            "rx": 400,
        }
        self.namespace["remember_user_streams"](state, [first], t0)
        first["tx"] = 150
        first["rx"] = 900
        self.namespace["remember_user_streams"](state, [first], t1)
        site = state["destinations"]["alice"]["cdn.example.com"]
        self.assertEqual(site["ip"], "192.0.2.8")
        self.assertEqual(site["upload"], 150)
        self.assertEqual(site["download"], 900)
        self.assertEqual(site["hits"], 1)
        self.assertEqual(site["first_seen"], t0)
        self.assertEqual(site["last_seen"], t1)

    def test_root_host_uses_registrable_domain(self):
        root = self.namespace["root_host"]
        self.assertEqual(root("bag.itunes.apple.com"), "apple.com")
        self.assertEqual(root("edge.microsoft.com"), "microsoft.com")
        self.assertEqual(root("192.0.2.8"), "192.0.2.8")
        self.assertEqual(root("foo.co.uk"), "foo.co.uk")

    def test_session_stats_pair_connect_and_disconnect(self):
        stats = self.namespace["session_stats_from_logs"](
            [
                '2026-09-16T10:00:00Z INFO client connected {"addr":"198.51.100.40:1234","id":"alice"}',
                '2026-09-16T10:05:00Z INFO client disconnected {"addr":"198.51.100.40:1234","id":"alice"}',
                '2026-09-16T10:00:00Z INFO client connected {"addr":"203.0.113.9:1","id":"bob"}',
            ],
            "alice",
        )
        self.assertEqual(stats["finished"], 1)
        self.assertEqual(stats["last_seconds"], 300)
        self.assertEqual(stats["by_ip"]["198.51.100.40"], 300)

    def test_sites_and_live_are_scoped_to_the_requested_user(self):
        self.namespace.update(
            {
                "STATE_FILE": self.root / "state.json",
                "hy2_is_off": lambda: False,
                "load_env": lambda: {"API_SECRET": "secret", "PUBLIC_IP": "203.0.113.9"},
                "hysteria_api": lambda path, secret, **kwargs: {
                    "streams": [
                        {
                            "auth": "alice",
                            "req_addr": "192.0.2.1:443",
                            "hooked_req_addr": "a.example:443",
                            "tx": 10,
                            "rx": 20,
                            "state": "estab",
                            "last_active_at": "now",
                        },
                        {
                            "auth": "bob",
                            "req_addr": "192.0.2.2:443",
                            "hooked_req_addr": "b.example:443",
                            "tx": 99,
                            "rx": 99,
                            "state": "estab",
                            "last_active_at": "now",
                        },
                    ]
                },
            }
        )
        (self.root / "state.json").write_text(
            json.dumps(
                {
                    "destinations": {
                        "alice": {
                            "a.example": {
                                "ip": "192.0.2.1",
                                "port": "443",
                                "upload": 10,
                                "download": 20,
                                "hits": 1,
                                "last_seen": datetime.now(timezone.utc).isoformat(
                                    timespec="seconds"
                                ),
                            }
                        },
                        "bob": {
                            "b.example": {
                                "ip": "192.0.2.2",
                                "port": "443",
                                "upload": 99,
                                "download": 99,
                                "hits": 3,
                                "last_seen": datetime.now(timezone.utc).isoformat(
                                    timespec="seconds"
                                ),
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        payload = self.analyze("alice")
        self.assertEqual(payload["live"][0]["host"], "a.example")
        self.assertEqual(len(payload["live"]), 1)
        self.assertEqual(payload["sites"][0]["host"], "a.example")
        self.assertEqual(len(payload["sites"]), 1)

    def test_forget_user_clears_destination_samples(self):
        state_file = self.root / "state.json"
        self.namespace["STATE_FILE"] = state_file
        state_file.write_text(
            json.dumps(
                {
                    "users": {"alice": {}, "bob": {}},
                    "destinations": {"alice": {"x": {}}, "bob": {"y": {}}},
                    "stream_bytes": {"alice:1:2": {"tx": 1, "rx": 1}, "bob:3:4": {"tx": 2, "rx": 2}},
                }
            ),
            encoding="utf-8",
        )
        self.namespace["forget_user_side_state"]("bob")
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertNotIn("bob", state["destinations"])
        self.assertNotIn("bob:3:4", state["stream_bytes"])
        self.assertIn("alice", state["destinations"])
        self.assertIn("alice:1:2", state["stream_bytes"])

    def test_hysteria_config_enables_sniff_for_hostnames(self):
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        self.assertIn("sniff:", config)
        self.assertIn("enable: true", config)
        backend = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")
        self.assertIn("/dump/streams", backend)


class UserTrafficPanelTests(unittest.TestCase):
    def test_user_menu_opens_traffic_analysis_modal(self):
        panel = (ROOT / "lib" / "panel.sh").read_text(encoding="utf-8")
        self.assertIn("流量分析", panel)
        self.assertIn("api/user/traffic", panel)
        self.assertIn('id="trafficModal"', panel)
        self.assertIn("menuItem(\"流量分析\"", panel)
        self.assertIn("#dbeafe", panel)
        self.assertIn("#b91c1c", panel)
        self.assertIn("时段热力", panel)
        self.assertIn("增量趋势", panel)
        self.assertIn("按日用量", panel)
        self.assertIn("上下行结构", panel)
        self.assertIn("出口 IP", panel)
        self.assertIn("当前连接", panel)
        self.assertIn("访问站点", panel)
        self.assertIn("客户端 IP", panel)
        self.assertIn('data-sort="total"', panel)
        self.assertIn('class="sortable"', panel)
        self.assertIn("bindSortHeaders", panel)
        self.assertIn('id="trafficSummary"', panel)
        self.assertIn("function relTime", panel)
        self.assertIn("weekdayName", panel)
        self.assertIn("site-bar-row", panel)
        self.assertIn("day-cols", panel)
        self.assertIn("buildTrafficSummary", panel)
        self.assertIn("min(1280px,96vw)", panel)
        self.assertIn("trafficMonthExtra", panel)
        self.assertIn("function svgNode", panel)
        self.assertIn("stack-bar", panel)
        self.assertIn('data-sort="port"', panel)
        self.assertIn("首次访问", panel)
        self.assertIn("最近访问", panel)
        self.assertIn("function formatClock", panel)
        self.assertIn("function visitCell", panel)
        self.assertIn('data-sort="first_seen"', panel)
        self.assertIn('data-sort="last_active"', panel)
        self.assertIn("client-cards", panel)
        self.assertIn("function portLabel", panel)
        self.assertIn("function streamState", panel)
        self.assertIn("trafficLiveCount", panel)
        self.assertIn('data-sort="share"', panel)
        self.assertIn("作息曲线", panel)
        self.assertIn("trafficHours", panel)
        self.assertIn("站点构成", panel)
        self.assertIn("trafficMix", panel)
        self.assertIn("function renderSiteMix", panel)
        self.assertIn("工作日 / 周末", panel)
        self.assertIn("def root_host", (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8"))
        self.assertIn("session_stats_from_logs", (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8"))
        self.assertIn("groupSitesByRoot", panel)
        self.assertIn("formatDuration", panel)


class ClientIpAndSortTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_backend_namespace()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.users_file = self.root / "users.json"
        self.data_file = self.root / "data.json"
        self.state_file = self.root / "state.json"
        self.users_file.write_text(
            json.dumps({"alice": {"password": "x", "token": "t", "disabled": False}}) + "\n",
            encoding="utf-8",
        )
        self.data_file.write_text(
            json.dumps({"server": {"traffic": {"used": 1}, "ip": "203.0.113.9"}, "users": []})
            + "\n",
            encoding="utf-8",
        )
        self.namespace.update(
            {
                "USERS_FILE": self.users_file,
                "DATA_FILE": self.data_file,
                "STATE_FILE": self.state_file,
                "HISTORY_CSV": self.root / "history.csv",
            }
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_parse_hysteria_connect_json_and_console(self):
        parse = self.namespace["parse_hysteria_connect_line"]
        self.assertEqual(
            parse(
                '{"level":"info","msg":"client connected","addr":"198.51.100.10:44321","id":"alice"}'
            ),
            ("alice", "198.51.100.10:44321"),
        )
        self.assertEqual(
            parse(
                'INFO\tclient connected\t{"addr": "198.51.100.11:1000", "id": "alice", "tx": 1}'
            ),
            ("alice", "198.51.100.11:1000"),
        )
        self.assertEqual(
            parse(
                'Sep 15 11:11:27 host hysteria[5105]: 2026-09-15T11:11:27Z        INFO        client connected        {"addr": "219.144.6.152:40540", "id": "user2", "tx": 0}'
            ),
            ("user2", "219.144.6.152:40540"),
        )
        self.assertEqual(
            parse(
                'Sep 15 11:08:47 host hysteria[5105]: 2026-09-15T11:08:47Z        WARN        TCP error        {"addr": "111.21.214.117:60252", "id": "user1", "reqAddr": "edge.microsoft.com:443", "error": "read tcp4 185.255.95.88:56606->150.171.30.11:443: read: connection reset by peer"}'
            ),
            ("user1", "111.21.214.117:60252"),
        )
        self.assertEqual(
            parse(
                'INFO        client disconnected        {"addr": "219.144.6.152:40548", "id": "user2", "error": "timeout"}'
            ),
            ("user2", "219.144.6.152:40548"),
        )
        self.assertIsNone(parse("client disconnected id=alice"))

    def test_stream_client_addr_reads_addr_fields(self):
        addr = self.namespace["stream_client_addr"]
        self.assertEqual(
            addr({"addr": "198.51.100.20:5555", "req_addr": "192.0.2.1:443"}),
            "198.51.100.20:5555",
        )
        self.assertEqual(addr({"client_addr": "198.51.100.21"}), "198.51.100.21")
        self.assertEqual(addr({"req_addr": "192.0.2.1:443"}), "")

    def test_remember_client_ips_from_streams_and_logs(self):
        state: dict = {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.namespace["remember_client_ips"](
            state,
            [
                {
                    "auth": "alice",
                    "addr": "198.51.100.30:6000",
                    "req_addr": "192.0.2.1:443",
                }
            ],
            [
                '{"msg":"client connected","addr":"198.51.100.31:7000","id":"alice"}',
                'INFO client connected {"addr": "203.0.113.9:1", "id": "bob"}',
            ],
            now,
        )
        alice = state["client_ips"]["alice"]
        self.assertIn("198.51.100.30", alice)
        self.assertIn("198.51.100.31", alice)
        self.assertIn("203.0.113.9", state["client_ips"]["bob"])
        self.assertEqual(alice["198.51.100.30"]["port"], "6000")

    def test_remember_log_destinations_from_tcp_error_once_per_host(self):
        state: dict = {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [
            'Sep 15 11:08:47 host hysteria[5105]: 2026-09-15T11:08:47Z        WARN        TCP error        {"addr": "111.21.214.117:61252", "id": "alice", "reqAddr": "edge.microsoft.com:443", "error": "x"}',
            'Sep 15 11:08:47 host hysteria[5105]: 2026-09-15T11:08:47Z        WARN        TCP error        {"addr": "111.21.214.117:61252", "id": "alice", "reqAddr": "edge.microsoft.com:443", "error": "y"}',
            'WARN        TCP error        {"addr": "111.21.214.117:61252", "id": "alice", "reqAddr": "aweme.snssdk.com%28null%29:443", "error": "z"}',
            '2026-09-15T11:09:10Z        WARN        TCP error        {"addr": "219.144.6.152:40540", "id": "bob", "reqAddr": "bag.itunes.apple.com:443", "error": "t"}',
        ]
        self.namespace["remember_log_destinations"](state, lines, now)
        alice = state["destinations"]["alice"]
        self.assertEqual(alice["edge.microsoft.com"]["hits"], 1)
        self.assertEqual(alice["edge.microsoft.com"]["port"], "443")
        self.assertTrue(alice["edge.microsoft.com"]["first_seen"].startswith("2026-09-15T11:08:47"))
        self.assertTrue(alice["edge.microsoft.com"]["last_seen"].startswith("2026-09-15T11:08:47"))
        self.assertNotIn("aweme.snssdk.com%28null%29", alice)
        self.assertIn("bag.itunes.apple.com", state["destinations"]["bob"])
        later = [
            '2026-09-15T12:00:00Z        WARN        TCP error        {"addr": "111.21.214.117:61252", "id": "alice", "reqAddr": "edge.microsoft.com:443", "error": "x"}',
        ]
        self.namespace["remember_log_destinations"](state, later, now)
        self.assertTrue(state["destinations"]["alice"]["edge.microsoft.com"]["first_seen"].startswith("2026-09-15T11:08:47"))
        self.assertTrue(state["destinations"]["alice"]["edge.microsoft.com"]["last_seen"].startswith("2026-09-15T12:00:00"))
        self.assertEqual(state["destinations"]["alice"]["edge.microsoft.com"]["hits"], 2)

    def test_log_only_sites_rank_by_hits_when_bytes_are_zero(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.namespace["hy2_is_off"] = lambda: True
        self.state_file.write_text(
            json.dumps(
                {
                    "destinations": {
                        "alice": {
                            "quiet.example": {
                                "ip": "",
                                "port": "443",
                                "upload": 0,
                                "download": 0,
                                "hits": 1,
                                "first_seen": now,
                                "last_seen": now,
                            },
                            "hot.example": {
                                "ip": "",
                                "port": "443",
                                "upload": 0,
                                "download": 0,
                                "hits": 9,
                                "first_seen": now,
                                "last_seen": now,
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        payload = self.namespace["user_traffic_analysis"]("alice")
        self.assertEqual([row["host"] for row in payload["sites"]], ["hot.example", "quiet.example"])
        self.assertEqual(payload["sites"][0]["first_seen"], now)
        self.assertEqual(payload["sites"][0]["last_seen"], now)

    def test_live_rows_reuse_user_client_ip_when_stream_has_none(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.state_file.write_text(
            json.dumps(
                {
                    "client_ips": {
                        "alice": {"198.51.100.40": {"port": "1234", "last_seen": now}}
                    }
                }
            ),
            encoding="utf-8",
        )
        self.namespace.update(
            {
                "hy2_is_off": lambda: False,
                "load_env": lambda: {"API_SECRET": "secret", "PUBLIC_IP": "203.0.113.9"},
                "hysteria_api": lambda path, secret, **kwargs: {
                    "streams": [
                        {
                            "auth": "alice",
                            "req_addr": "192.0.2.1:443",
                            "hooked_req_addr": "a.example:443",
                            "tx": 10,
                            "rx": 20,
                            "state": "estab",
                        }
                    ]
                },
            }
        )
        payload = self.namespace["user_traffic_analysis"]("alice")
        self.assertEqual(payload["live"][0]["client"], "198.51.100.40")
        self.assertEqual(payload["live"][0]["client_port"], "1234")

    def test_traffic_analysis_exposes_client_ips_and_live_client(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.state_file.write_text(
            json.dumps(
                {
                    "client_ips": {
                        "alice": {
                            "198.51.100.40": {
                                "port": "1234",
                                "last_seen": now,
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        self.namespace.update(
            {
                "hy2_is_off": lambda: False,
                "load_env": lambda: {"API_SECRET": "secret", "PUBLIC_IP": "203.0.113.9"},
                "hysteria_api": lambda path, secret, **kwargs: {
                    "streams": [
                        {
                            "auth": "alice",
                            "addr": "198.51.100.40:1234",
                            "req_addr": "192.0.2.1:443",
                            "hooked_req_addr": "a.example:443",
                            "tx": 10,
                            "rx": 20,
                            "state": "estab",
                        }
                    ]
                },
            }
        )
        payload = self.namespace["user_traffic_analysis"]("alice")
        self.assertEqual(payload["client_ips"][0]["ip"], "198.51.100.40")
        self.assertEqual(payload["live"][0]["client"], "198.51.100.40")
        self.assertEqual(payload["live"][0]["client_port"], "1234")

    def test_forget_user_clears_client_ips(self):
        self.state_file.write_text(
            json.dumps(
                {
                    "users": {"alice": {}, "bob": {}},
                    "client_ips": {
                        "alice": {"1.1.1.1": {"port": "1", "last_seen": "x"}},
                        "bob": {"2.2.2.2": {"port": "2", "last_seen": "x"}},
                    },
                }
            ),
            encoding="utf-8",
        )
        self.namespace["forget_user_side_state"]("bob")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertNotIn("bob", state["client_ips"])
        self.assertIn("alice", state["client_ips"])


if __name__ == "__main__":
    unittest.main()
