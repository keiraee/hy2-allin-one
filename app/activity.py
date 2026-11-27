#!/usr/bin/env python3
"""User activity tracking: connect-log parsing, client IPs, live streams, sites, and history series."""
from __future__ import annotations

import csv
import ipaddress
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

for _cand in (
    str(Path(__file__).resolve().parent) if "__file__" in globals() else "",
    "/usr/local/lib/hy2-aio",
    str(Path.cwd() / "app"),
):
    if _cand and _cand not in sys.path and (Path(_cand) / "common.py").is_file():
        sys.path.insert(0, _cand)

from common import counter_delta


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")
TRAFFIC_HISTORY_DAYS = 7
DEST_MAX_PER_USER = 80
CLIENT_IP_MAX = 8
CLIENT_ADDR_KEYS = ("addr", "client_addr", "remote_addr", "src_addr")
LOG_ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)


def canonical_username(name: str, users: Optional[dict[str, Any]] = None) -> str:
    text = str(name or "").strip()
    if not text:
        return text
    roster = users if isinstance(users, dict) else {}
    if text in roster:
        return text
    lowered = text.casefold()
    aliases = [key for key in roster if str(key).casefold() == lowered]
    if len(aliases) == 1:
        return str(aliases[0])
    return text


def mapping_get_ci(
    mapping: Any, username: str, users: Optional[dict[str, Any]] = None
) -> Any:
    if not isinstance(mapping, dict):
        return None
    if username in mapping:
        return mapping[username]
    roster = users if isinstance(users, dict) else {}
    lowered = str(username).casefold()
    aliases = [key for key in roster if str(key).casefold() == lowered]
    if len(aliases) != 1:
        return None
    found = None
    hits = 0
    for key, value in mapping.items():
        if str(key).casefold() == lowered:
            found = value
            hits += 1
    return found if hits == 1 else None


def nested_bucket_ci(
    mapping: Any, username: str, users: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    roster = users if isinstance(users, dict) else {}
    lowered = str(username).casefold()
    aliases = [key for key in roster if str(key).casefold() == lowered]
    keys = [username] if username in mapping else []
    if len(aliases) == 1:
        keys = [key for key in mapping if str(key).casefold() == lowered]
        if username in keys:
            keys = [username] + [key for key in keys if key != username]
    merged: dict[str, Any] = {}
    for key in keys:
        value = mapping.get(key)
        if not isinstance(value, dict):
            continue
        for inner_key, inner_value in value.items():
            if inner_key not in merged:
                merged[inner_key] = inner_value
    return merged


def split_host_port(addr: str) -> tuple[str, str]:
    text = str(addr or "").strip()
    if not text:
        return "", ""
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return text.strip("[]"), ""
        host = text[1:end]
        rest = text[end + 1 :]
        return host, rest[1:] if rest.startswith(":") else ""
    if text.count(":") == 1:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            return host, port
    return text, ""


def is_ip_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


MULTI_TLDS = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "com.au",
    "net.au",
    "org.au",
    "com.cn",
    "net.cn",
    "org.cn",
    "gov.cn",
    "edu.cn",
    "com.hk",
    "com.tw",
    "com.sg",
    "co.jp",
    "ne.jp",
    "or.jp",
    "ac.jp",
}


def root_host(host: str) -> str:
    text = str(host or "").strip().lower().strip(".")
    if not text:
        return ""
    if is_ip_host(text):
        return text
    parts = [item for item in text.split(".") if item]
    if len(parts) <= 2:
        return text
    tail2 = ".".join(parts[-2:])
    if tail2 in MULTI_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return tail2


def stream_client_addr(stream: dict[str, Any]) -> str:
    if not isinstance(stream, dict):
        return ""
    for key in CLIENT_ADDR_KEYS:
        raw = str(stream.get(key) or "").strip()
        if raw:
            return raw
    return ""


def parse_hysteria_connect_line(line: str) -> Optional[tuple[str, str]]:
    text = str(line or "").strip()
    lowered = text.lower()
    if not (
        "client connected" in lowered
        or "client disconnected" in lowered
        or "tcp error" in lowered
    ):
        return None
    user = ""
    addr = ""
    start = text.find("{")
    blob = text[start:] if start != -1 else ""
    if blob:
        try:
            obj = json.loads(blob)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            user = str(obj.get("id") or "").strip()
            addr = str(obj.get("addr") or "").strip()
        if not user or not addr:
            addr_m = re.search(r'"addr"\s*:\s*"([^"]+)"', blob)
            id_m = re.search(r'"id"\s*:\s*"([^"]+)"', blob)
            if addr_m:
                addr = addr or addr_m.group(1).strip()
            if id_m:
                user = user or id_m.group(1).strip()
    if user and addr:
        return user, addr
    return None


def session_stats_from_logs(
    log_lines: list[str], username: str, users: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    opens: dict[str, datetime] = {}
    durations: list[int] = []
    last_by_ip: dict[str, int] = {}
    for line in log_lines or []:
        text = str(line or "")
        lowered = text.lower()
        if "tcp error" in lowered and "client connected" not in lowered:
            continue
        parsed = parse_hysteria_connect_line(text)
        if not parsed or canonical_username(parsed[0], users) != username:
            continue
        stamp = parse_history_time(stamp_from_log_line(text, ""))
        if stamp is None:
            continue
        addr = parsed[1]
        host, _port = split_host_port(addr)
        if "client disconnected" in lowered:
            start = opens.pop(addr, None)
            if start is None and host:
                start = next(
                    (opens.pop(key) for key in list(opens) if key.startswith(host + ":") or key == host),
                    None,
                )
            if start is not None:
                seconds = max(0, int((stamp - start).total_seconds()))
                durations.append(seconds)
                if host:
                    last_by_ip[host] = seconds
        elif "client connected" in lowered:
            opens[addr] = stamp
    now = datetime.now(timezone.utc)
    open_seconds = 0
    for addr, start in opens.items():
        host, _port = split_host_port(addr)
        seconds = max(0, int((now - start).total_seconds()))
        open_seconds += 1
        if host and host not in last_by_ip:
            last_by_ip[host] = seconds
    finished = len(durations)
    avg = int(sum(durations) / finished) if finished else 0
    return {
        "count": finished + open_seconds,
        "finished": finished,
        "avg_seconds": avg,
        "last_seconds": durations[-1] if durations else 0,
        "by_ip": last_by_ip,
    }


def record_client_ip(
    state: dict[str, Any], username: str, addr: str, timestamp: str
) -> None:
    host, port = split_host_port(addr)
    if not host or not USERNAME_PATTERN.fullmatch(username):
        return
    bucket = state.setdefault("client_ips", {})
    if not isinstance(bucket, dict):
        bucket = {}
        state["client_ips"] = bucket
    items = bucket.get(username)
    if not isinstance(items, dict):
        items = {}
        bucket[username] = items
    item = items.get(host)
    if not isinstance(item, dict):
        item = {"port": "", "last_seen": ""}
        items[host] = item
    if port:
        item["port"] = port
    incoming = parse_history_time(timestamp)
    current = parse_history_time(str(item.get("last_seen") or ""))
    if incoming is not None:
        if current is None or incoming >= current:
            item["last_seen"] = incoming.isoformat(timespec="seconds")
    elif not str(item.get("last_seen") or "").strip():
        item["last_seen"] = timestamp


def prune_client_ips(state: dict[str, Any]) -> None:
    bucket = state.get("client_ips")
    if not isinstance(bucket, dict):
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRAFFIC_HISTORY_DAYS)
    for user, items in list(bucket.items()):
        if not isinstance(items, dict):
            bucket.pop(user, None)
            continue
        for ip, info in list(items.items()):
            if not isinstance(info, dict):
                items.pop(ip, None)
                continue
            seen_at = parse_history_time(str(info.get("last_seen", "")))
            if seen_at is None or seen_at < cutoff:
                items.pop(ip, None)
        ranked = sorted(
            items.items(),
            key=lambda kv: str((kv[1] or {}).get("last_seen") or ""),
            reverse=True,
        )
        bucket[user] = {name: info for name, info in ranked[:CLIENT_IP_MAX]}
        if not bucket[user]:
            bucket.pop(user, None)


def is_plausible_host(host: str) -> bool:
    text = str(host or "").strip().strip(".")
    if not text or "%" in text or " " in text or len(text) > 253:
        return False
    if is_ip_host(text):
        return True
    if not re.fullmatch(r"[A-Za-z0-9._-]+", text):
        return False
    return "." in text or text.lower() == "localhost"


def stamp_from_log_line(line: str, fallback: str = "") -> str:
    match = LOG_ISO_RE.search(str(line or ""))
    if match:
        parsed = parse_history_time(match.group(0))
        if parsed is not None:
            return parsed.isoformat(timespec="seconds")
    parsed = parse_history_time(fallback)
    if parsed is not None:
        return parsed.isoformat(timespec="seconds")
    return str(fallback or "").strip()


def apply_seen_time(item: dict[str, Any], stamp: str) -> None:
    stamp = str(stamp or "").strip()
    if not stamp:
        return
    parsed = parse_history_time(stamp)
    if parsed is not None:
        stamp = parsed.isoformat(timespec="seconds")
    if not str(item.get("first_seen") or "").strip():
        item["first_seen"] = str(item.get("last_seen") or "").strip() or stamp
    current = parse_history_time(str(item.get("last_seen") or ""))
    incoming = parse_history_time(stamp)
    if incoming is None:
        if not str(item.get("last_seen") or "").strip():
            item["last_seen"] = stamp
        return
    if current is None or incoming >= current:
        item["last_seen"] = incoming.isoformat(timespec="seconds")


def remember_log_destinations(
    state: dict[str, Any],
    log_lines: list[str],
    timestamp: str,
    users: Optional[dict[str, Any]] = None,
) -> None:
    if not isinstance(state, dict):
        return
    dest = state.setdefault("destinations", {})
    if not isinstance(dest, dict):
        dest = {}
        state["destinations"] = dest
    created: set[tuple[str, str]] = set()
    for line in log_lines or []:
        text = str(line or "")
        if "tcp error" not in text.lower():
            continue
        start = text.find("{")
        if start == -1:
            continue
        try:
            obj = json.loads(text[start:])
        except Exception:
            obj = None
        if not isinstance(obj, dict):
            continue
        user = canonical_username(str(obj.get("id", users) or "").strip())
        req = str(obj.get("reqAddr") or obj.get("req_addr") or "").strip()
        if not user or not req or not USERNAME_PATTERN.fullmatch(user):
            continue
        host, port = split_host_port(req)
        if not is_plausible_host(host):
            continue
        bucket = dest.get(user)
        if not isinstance(bucket, dict):
            bucket = {}
            dest[user] = bucket
        item = bucket.get(host)
        if not isinstance(item, dict):
            item = {
                "ip": "",
                "port": "",
                "upload": 0,
                "download": 0,
                "hits": 0,
                "first_seen": "",
                "last_seen": "",
            }
            bucket[host] = item
        if is_ip_host(host):
            item["ip"] = host
        if port:
            item["port"] = port
        line_stamp = stamp_from_log_line(text, timestamp)
        prev_last = parse_history_time(str(item.get("last_seen") or ""))
        incoming_last = parse_history_time(line_stamp)
        is_newer = prev_last is None or (incoming_last is not None and incoming_last > prev_last)
        apply_seen_time(item, line_stamp)
        key = (user, host)
        if is_newer and key not in created:
            item["hits"] = int(item.get("hits", 0) or 0) + 1
            created.add(key)
    for user, bucket in list(dest.items()):
        if not isinstance(bucket, dict):
            dest.pop(user, None)
            continue
        ranked = sorted(
            bucket.items(),
            key=lambda kv: (
                int((kv[1] or {}).get("upload", 0) or 0)
                + int((kv[1] or {}).get("download", 0) or 0)
                + int((kv[1] or {}).get("hits", 0) or 0),
                str((kv[1] or {}).get("last_seen") or ""),
            ),
            reverse=True,
        )
        dest[user] = {name: info for name, info in ranked[:DEST_MAX_PER_USER]}
        if not dest[user]:
            dest.pop(user, None)


def remember_client_ips(
    state: dict[str, Any],
    streams: list[Any],
    log_lines: list[str],
    timestamp: str,
    users: Optional[dict[str, Any]] = None,
) -> None:
    if not isinstance(state, dict):
        return
    if not isinstance(streams, list):
        streams = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        user = canonical_username(str(stream.get("auth", users) or "").strip())
        addr = stream_client_addr(stream)
        if user and addr:
            record_client_ip(state, user, addr, timestamp)
    for line in log_lines or []:
        parsed = parse_hysteria_connect_line(str(line))
        if not parsed:
            continue
        record_client_ip(
            state,
            canonical_username(parsed[0], users),
            parsed[1],
            stamp_from_log_line(str(line), timestamp),
        )
    prune_client_ips(state)


def client_ips_for_user(
    state: Any, username: str, users: Optional[dict[str, Any]] = None
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    bucket: dict[str, Any] = {}
    if isinstance(state, dict):
        stored = state.get("client_ips")
        bucket = nested_bucket_ci(stored, username, users)
    for ip, info in bucket.items():
        if not isinstance(info, dict):
            continue
        rows.append(
            {
                "ip": str(ip),
                "port": str(info.get("port") or ""),
                "last_seen": str(info.get("last_seen") or ""),
            }
        )
    rows.sort(key=lambda item: item["last_seen"], reverse=True)
    return rows[:CLIENT_IP_MAX]


def hysteria_connect_log_lines() -> list[str]:
    try:
        result = subprocess.run(
            [
                "journalctl",
                "-u",
                "hysteria-server.service",
                "--since",
                "15 min ago",
                "-n",
                "800",
                "-o",
                "cat",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return []
    return result.stdout.splitlines() if result.stdout else []


def stream_target(stream: dict[str, Any]) -> dict[str, str]:
    hooked_host, hooked_port = split_host_port(str(stream.get("hooked_req_addr") or ""))
    req_host, req_port = split_host_port(str(stream.get("req_addr") or ""))
    port = hooked_port or req_port
    ip = ""
    if is_ip_host(req_host):
        ip = req_host
    elif is_ip_host(hooked_host):
        ip = hooked_host
    host = ""
    if hooked_host and not is_ip_host(hooked_host):
        host = hooked_host
    elif req_host and not is_ip_host(req_host):
        host = req_host
    else:
        host = ip or hooked_host or req_host
    return {"host": host, "ip": ip, "port": port}


def normalize_streams_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw = payload.get("streams", [])
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def remember_user_streams(
    state: dict[str, Any],
    streams: list[Any],
    timestamp: str,
    users: Optional[dict[str, Any]] = None,
) -> None:
    seen = state.setdefault("stream_bytes", {})
    dest = state.setdefault("destinations", {})
    if not isinstance(seen, dict):
        seen = {}
        state["stream_bytes"] = seen
    if not isinstance(dest, dict):
        dest = {}
        state["destinations"] = dest
    current: set[str] = set()
    if not isinstance(streams, list):
        streams = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        user = canonical_username(str(stream.get("auth", users) or "").strip())
        if not user:
            continue
        key = f"{user}:{stream.get('connection')}:{stream.get('stream')}"
        current.add(key)
        try:
            tx = int(stream.get("tx") or 0)
            rx = int(stream.get("rx") or 0)
        except (TypeError, ValueError):
            tx = rx = 0
        prev = seen.get(key)
        first = not isinstance(prev, dict)
        prev_tx = int((prev or {}).get("tx", 0) or 0) if isinstance(prev, dict) else 0
        prev_rx = int((prev or {}).get("rx", 0) or 0) if isinstance(prev, dict) else 0
        dtx = counter_delta(tx, prev_tx)
        drx = counter_delta(rx, prev_rx)
        seen[key] = {"tx": tx, "rx": rx}
        target = stream_target(stream)
        host = target["host"] or target["ip"] or "unknown"
        bucket = dest.setdefault(user, {})
        if not isinstance(bucket, dict):
            bucket = {}
            dest[user] = bucket
        item = bucket.get(host)
        if not isinstance(item, dict):
            item = {
                "ip": "",
                "port": "",
                "upload": 0,
                "download": 0,
                "hits": 0,
                "first_seen": "",
                "last_seen": "",
            }
            bucket[host] = item
        if target["ip"]:
            item["ip"] = target["ip"]
        if target["port"]:
            item["port"] = target["port"]
        item["upload"] = int(item.get("upload", 0) or 0) + dtx
        item["download"] = int(item.get("download", 0) or 0) + drx
        if first:
            item["hits"] = int(item.get("hits", 0) or 0) + 1
        apply_seen_time(
            item,
            str(stream.get("last_active_at") or stream.get("started_at") or timestamp),
        )
    for stale in [key for key in list(seen) if key not in current]:
        seen.pop(stale, None)
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRAFFIC_HISTORY_DAYS)
    for user, bucket in list(dest.items()):
        if not isinstance(bucket, dict):
            dest.pop(user, None)
            continue
        for host, item in list(bucket.items()):
            if not isinstance(item, dict):
                bucket.pop(host, None)
                continue
            seen_at = parse_history_time(str(item.get("last_seen", "")))
            if seen_at is None or seen_at < cutoff:
                bucket.pop(host, None)
        ranked = sorted(
            bucket.items(),
            key=lambda kv: int((kv[1] or {}).get("upload", 0) or 0)
            + int((kv[1] or {}).get("download", 0) or 0),
            reverse=True,
        )
        dest[user] = {name: info for name, info in ranked[:DEST_MAX_PER_USER]}
        if not dest[user]:
            dest.pop(user, None)


def live_streams_from_payload(
    payload: Any, username: str, users: Optional[dict[str, Any]] = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stream in normalize_streams_payload(payload):
        if canonical_username(str(stream.get("auth", users) or "").strip(), users) != username:
            continue
        target = stream_target(stream)
        client_raw = stream_client_addr(stream)
        client_host, client_port = split_host_port(client_raw)
        try:
            upload = int(stream.get("tx") or 0)
            download = int(stream.get("rx") or 0)
        except (TypeError, ValueError):
            upload = download = 0
        rows.append(
            {
                "host": target["host"] or target["ip"] or "unknown",
                "ip": target["ip"],
                "port": target["port"],
                "client": client_host,
                "client_port": client_port,
                "upload": upload,
                "download": download,
                "state": str(stream.get("state") or ""),
                "last_active": str(stream.get("last_active_at") or ""),
            }
        )
    rows.sort(key=lambda row: row["upload"] + row["download"], reverse=True)
    return rows[:DEST_MAX_PER_USER]


def sites_from_state(
    state: Any, username: str, users: Optional[dict[str, Any]] = None
) -> list[dict[str, Any]]:
    bucket: dict[str, Any] = {}
    if isinstance(state, dict):
        dest = state.get("destinations")
        bucket = nested_bucket_ci(dest, username, users)
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRAFFIC_HISTORY_DAYS)
    rows: list[dict[str, Any]] = []
    for host, item in bucket.items():
        if not isinstance(item, dict):
            continue
        seen_at = parse_history_time(str(item.get("last_seen", "")))
        if seen_at is not None and seen_at < cutoff:
            continue
        upload = int(item.get("upload", 0) or 0)
        download = int(item.get("download", 0) or 0)
        rows.append(
            {
                "host": str(host),
                "root": root_host(str(host)),
                "ip": str(item.get("ip") or ""),
                "port": str(item.get("port") or ""),
                "upload": upload,
                "download": download,
                "total": upload + download,
                "hits": int(item.get("hits", 0) or 0),
                "first_seen": str(item.get("first_seen") or item.get("last_seen") or ""),
                "last_seen": str(item.get("last_seen") or ""),
            }
        )
    rows.sort(key=lambda row: (row["total"], row["hits"]), reverse=True)
    return rows[:DEST_MAX_PER_USER]


def parse_history_time(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def history_files(history_csv: Path) -> list[Path]:
    files: list[Path] = []
    rotated = history_csv.with_name("history.csv.1")
    if rotated.exists():
        files.append(rotated)
    if history_csv.exists():
        files.append(history_csv)
    return files


def load_user_history_rows(
    history_csv: Path, username: str
) -> list[tuple[datetime, int, int]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRAFFIC_HISTORY_DAYS)
    rows: list[tuple[datetime, int, int]] = []
    for path in history_files(history_csv):
        try:
            with path.open(newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for item in reader:
                    if str(item.get("用户", "")).strip() != username:
                        continue
                    stamp = parse_history_time(str(item.get("时间", "")))
                    if stamp is None or stamp < cutoff:
                        continue
                    try:
                        upload = int(item.get("用户上传", 0) or 0)
                        download = int(item.get("用户下载", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    rows.append((stamp, max(upload, 0), max(download, 0)))
        except OSError:
            continue
    rows.sort(key=lambda item: item[0])
    return rows


def series_from_history(rows: list[tuple[datetime, int, int]]) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    prev_up: Optional[int] = None
    prev_down: Optional[int] = None
    for stamp, upload, download in rows:
        if prev_up is None or prev_down is None:
            prev_up, prev_down = upload, download
            continue
        up = counter_delta(upload, prev_up)
        down = counter_delta(download, prev_down)
        prev_up, prev_down = upload, download
        series.append(
            {
                "t": stamp.isoformat(timespec="seconds"),
                "up": up,
                "down": down,
            }
        )
    return series
