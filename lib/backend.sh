#!/usr/bin/env bash
# backend.sh - 后端 Python 服务生成

write_backend() {
  cat > "$APP_FILE" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import csv
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

ENV_FILE = Path("/etc/hy2-aio/config.env")
USERS_FILE = Path("/etc/hy2-aio/users.json")
MODE_FILE = Path("/etc/hy2-aio/client-mode.json")
STATE_DIR = Path("/var/lib/hy2-aio")
STATE_FILE = STATE_DIR / "state.json"
BACKUP_DIR = STATE_DIR / "backups"
REBUILD_FILE = Path("/usr/local/lib/hy2-aio/rebuild_config.py")
WEB_DIR = Path("/var/www/hy2-aio")
DOWNLOAD_DIR = WEB_DIR / "downloads"
DATA_FILE = WEB_DIR / "data.json"
USERS_CSV = WEB_DIR / "users.csv"
HISTORY_CSV = WEB_DIR / "history.csv"
LISTEN = ("127.0.0.1", 18081)
LOCK = threading.RLock()


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_users() -> dict[str, dict[str, str]]:
    data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("users.json 格式错误")
    return data


def normalize_mode(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    mode = str(value.get("mode", "bbr")).lower()
    if mode != "brutal":
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    if up <= 0 or down <= 0:
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    return {"mode": "brutal", "up_mbps": up, "down_mbps": down}


def load_modes() -> dict[str, Any]:
    data = read_json(MODE_FILE, {})
    if isinstance(data, dict) and "mode" in data:
        return {"default": normalize_mode(data), "users": {}}
    if not isinstance(data, dict):
        data = {}
    overrides = data.get("users", {})
    return {
        "default": normalize_mode(data.get("default", {})),
        "users": overrides if isinstance(overrides, dict) else {},
    }


def mode_for_user(username: str, modes: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    modes = modes or load_modes()
    overrides = modes.get("users", {})
    if isinstance(overrides, dict) and username in overrides:
        return normalize_mode(overrides[username])
    return normalize_mode(modes.get("default", {}))


def mode_label(mode: dict[str, Any]) -> str:
    if mode.get("mode") != "brutal":
        return "BBR 自动估速"
    up = float(mode.get("up_mbps", 0))
    down = float(mode.get("down_mbps", 0))
    return f"Brutal ↑{up:g} / ↓{down:g} Mbps"


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def net_counters(iface: str) -> tuple[int, int]:
    base = Path("/sys/class/net") / iface / "statistics"
    rx = int((base / "rx_bytes").read_text(encoding="utf-8").strip())
    tx = int((base / "tx_bytes").read_text(encoding="utf-8").strip())
    return rx, tx


def hysteria_api(path: str, secret: str) -> Any:
    stats_port = load_env().get("STATS_PORT", "9999")
    request = urllib.request.Request(
        f"http://127.0.0.1:{stats_port}" + path,
        headers={"Authorization": secret, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def service_status(name: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", name],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def cpu_percent() -> float:
    def read() -> tuple[int, int]:
        parts = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        values = [int(item) for item in parts]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return total, idle

    total1, idle1 = read()
    time.sleep(0.12)
    total2, idle2 = read()
    delta = max(total2 - total1, 1)
    return round((1 - (idle2 - idle1) / delta) * 100, 1)


def memory_info() -> dict[str, Any]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0]) * 1024
    total = values["MemTotal"]
    used = total - values["MemAvailable"]
    swap_total = values.get("SwapTotal", 0)
    swap_used = swap_total - values.get("SwapFree", 0)
    return {
        "total": total,
        "used": used,
        "percent": round(used / total * 100, 1),
        "swap_total": swap_total,
        "swap_used": swap_used,
        "swap_percent": round(swap_used / swap_total * 100, 1) if swap_total else 0,
    }


def client_insecure(env: dict[str, str]) -> bool:
    raw = str(env.get("CLIENT_INSECURE", "")).strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    domain = str(env.get("DOMAIN", ""))
    public_ip = str(env.get("PUBLIC_IP", ""))
    return domain.endswith("sslip.io") or domain == public_ip


def public_base_url(env: dict[str, str]) -> str:
    """Panel/subscription base URL (HTTPS except plain port 80)."""
    domain = str(env.get("DOMAIN", "") or "")
    port = str(env.get("PANEL_PORT", "443") or "443")
    if port == "80":
        return f"http://{domain}"
    if port in ("443", ""):
        return f"https://{domain}"
    return f"https://{domain}:{port}"


def direct_link(env: dict[str, str], username: str, password: str) -> str:
    auth = urllib.parse.quote(f"{username}:{password}", safe="")
    query_items = {
        "obfs": "salamander",
        "obfs-password": env["OBFS_PASSWORD"],
        "sni": env.get("SNI", "www.amazon.sg"),
    }
    if client_insecure(env):
        query_items["insecure"] = "1"
    query = urllib.parse.urlencode(query_items)
    name = urllib.parse.quote(f"HY2-{username}", safe="")
    return f"hysteria2://{auth}@{env['PUBLIC_IP']}:{env.get('HY2_PORT', '443')}/?{query}#{name}"


def subscription_yaml(env: dict[str, str], username: str, password: str) -> bytes:
    def q(value: str) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    mode = mode_for_user(username)
    rate_lines = ""
    if mode.get("mode") == "brutal":
        rate_lines = (
            f'    up: "{float(mode["up_mbps"]):g} Mbps"\n'
            f'    down: "{float(mode["down_mbps"]):g} Mbps"\n'
        )

    content = f"""mixed-port: 7890
allow-lan: false
mode: global
log-level: info
ipv6: false

tun:
  enable: true
  stack: system
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  route-exclude-address:
    - {q(env["PUBLIC_IP"] + "/32")}
  dns-hijack:
    - any:53
    - tcp://any:53

dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  nameserver:
    - https://1.1.1.1/dns-query
    - https://8.8.8.8/dns-query

proxy-groups:
  - name: "GLOBAL"
    type: select
    proxies:
      - {q("HY2-" + username)}

proxies:
  - name: {q("HY2-" + username)}
    type: hysteria2
    server: {q(env["PUBLIC_IP"])}
    port: {env.get('HY2_PORT', '443')}
{rate_lines}    password: {q(username + ":" + password)}
    obfs: salamander
    obfs-password: {q(env["OBFS_PASSWORD"])}
    sni: {q(env.get("SNI", "www.amazon.sg"))}
    skip-cert-verify: {"true" if client_insecure(env) else "false"}
    udp: true
    keepalive: 30s
"""
    return content.encode("utf-8")


def blank_state(iface: str) -> dict[str, Any]:
    rx, tx = net_counters(iface)
    return {
        "month": current_month(),
        "network": {"rx": rx, "tx": tx, "last_rx": rx, "last_tx": tx},
        "users": {},
        "last_history": 0,
    }


def collect(force_backup: bool = False) -> dict[str, Any]:
    with LOCK:
        env = load_env()
        users = load_users()
        modes = load_modes()
        iface = env["NETWORK_INTERFACE"]
        total_limit = int(env["TOTAL_BYTES"])
        state = read_json(STATE_FILE, blank_state(iface))

        now_month = current_month()
        raw_rx, raw_tx = net_counters(iface)
        if state.get("month") != now_month:
            state["month"] = now_month
            state["network"] = {"rx": 0, "tx": 0, "last_rx": raw_rx, "last_tx": raw_tx}
            for user_state in state.get("users", {}).values():
                user_state["month_tx"] = 0
                user_state["month_rx"] = 0

        network = state.setdefault("network", {})
        last_rx = int(network.get("last_rx", raw_rx))
        last_tx = int(network.get("last_tx", raw_tx))
        delta_rx = raw_rx - last_rx if raw_rx >= last_rx else raw_rx
        delta_tx = raw_tx - last_tx if raw_tx >= last_tx else raw_tx
        network["rx"] = int(network.get("rx", 0)) + max(delta_rx, 0)
        network["tx"] = int(network.get("tx", 0)) + max(delta_tx, 0)
        network["last_rx"] = raw_rx
        network["last_tx"] = raw_tx

        errors: list[str] = []
        try:
            traffic = hysteria_api("/traffic?clear=1", env["API_SECRET"])
            if not isinstance(traffic, dict):
                traffic = {}
        except Exception as error:
            traffic = {}
            errors.append(f"traffic API: {error}")

        try:
            online = hysteria_api("/online", env["API_SECRET"])
            if not isinstance(online, dict):
                online = {}
        except Exception as error:
            online = {}
            errors.append(f"online API: {error}")

        state_users = state.setdefault("users", {})
        output_users: list[dict[str, Any]] = []
        timestamp = iso_now()

        for username, info in sorted(users.items()):
            user_state = state_users.setdefault(
                username,
                {
                    "month_tx": 0,
                    "month_rx": 0,
                    "lifetime_tx": 0,
                    "lifetime_rx": 0,
                    "last_active": "从未",
                },
            )
            raw = traffic.get(username, {})
            raw = raw if isinstance(raw, dict) else {}
            tx = int(raw.get("tx", 0))
            rx = int(raw.get("rx", 0))
            user_state["month_tx"] = int(user_state.get("month_tx", 0)) + tx
            user_state["month_rx"] = int(user_state.get("month_rx", 0)) + rx
            user_state["lifetime_tx"] = int(user_state.get("lifetime_tx", 0)) + tx
            user_state["lifetime_rx"] = int(user_state.get("lifetime_rx", 0)) + rx
            devices = int(online.get(username, 0) or 0)
            if tx or rx or devices:
                user_state["last_active"] = timestamp

            client_mode = mode_for_user(username, modes)
            output_users.append(
                {
                    "username": username,
                    "note": str(info.get("note", "")),
                    "disabled": bool(info.get("disabled", False)),
                    "online": devices,
                    "upload": user_state["month_tx"],
                    "download": user_state["month_rx"],
                    "total": user_state["month_tx"] + user_state["month_rx"],
                    "lifetime_total": user_state["lifetime_tx"] + user_state["lifetime_rx"],
                    "last_active": user_state["last_active"],
                    "mode": mode_label(client_mode),
                }
            )

        disk = shutil.disk_usage("/")
        memory = memory_info()
        uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        loads = [round(value, 2) for value in os.getloadavg()]
        used = int(network["rx"]) + int(network["tx"])

        data = {
            "version": env.get("AIO_VERSION", "unknown"),
            "generated_at": timestamp,
            "errors": errors,
            "server": {
                "ip": env["PUBLIC_IP"],
                "domain": env["DOMAIN"],
                "hostname": socket.gethostname(),
                "interface": iface,
                "uptime": uptime,
                "cpu": cpu_percent(),
                "load": loads,
                "memory": memory,
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "percent": round(disk.used / disk.total * 100, 1),
                },
                "services": {
                    "Hysteria": service_status("hysteria-server.service"),
                    "HY2 AIO": service_status("hy2-aio.service"),
                    "Caddy": service_status("caddy.service"),
                },
                "traffic": {
                    "rx": int(network["rx"]),
                    "tx": int(network["tx"]),
                    "used": used,
                    "limit": total_limit,
                    "remain": max(total_limit - used, 0),
                    "percent": round(used / total_limit * 100, 4) if total_limit else 0,
                },
            },
            "client_mode_default": mode_label(normalize_mode(modes.get("default", {}))),
            "summary": {
                "users": len(output_users),
                "online_users": sum(1 for item in output_users if item["online"]),
                "devices": sum(item["online"] for item in output_users),
            },
            "users": output_users,
        }

        atomic_json(STATE_FILE, state)
        atomic_json(DATA_FILE, data)
        write_users_csv(output_users)
        write_history(state, data)
        create_backup(force=force_backup)
        apply_web_permissions()
        return data


def write_users_csv(users: list[dict[str, Any]]) -> None:
    temporary = USERS_CSV.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["用户", "在线设备", "月上传字节", "月下载字节", "月合计字节",
             "历史累计字节", "最后活动", "速率模式"]
        )
        for user in users:
            writer.writerow(
                [
                    user["username"], user["online"], user["upload"], user["download"],
                    user["total"], user["lifetime_total"], user["last_active"],
                    user["mode"],
                ]
            )
    os.replace(temporary, USERS_CSV)


HISTORY_MAX_BYTES = 5 * 1024 * 1024


def rotate_history_if_needed() -> None:
    if not HISTORY_CSV.exists() or HISTORY_CSV.stat().st_size < HISTORY_MAX_BYTES:
        return
    rotated = HISTORY_CSV.with_name("history.csv.1")
    if rotated.exists():
        rotated.unlink()
    HISTORY_CSV.replace(rotated)


def write_history(state: dict[str, Any], data: dict[str, Any]) -> None:
    now = time.time()
    if now - float(state.get("last_history", 0)) < 300:
        return
    rotate_history_if_needed()
    exists = HISTORY_CSV.exists()
    with HISTORY_CSV.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not exists:
            writer.writerow(
                ["时间", "整机接收", "整机发送", "整机合计", "CPU", "内存百分比",
                 "用户", "在线设备", "用户上传", "用户下载", "用户合计"]
            )
        traffic = data["server"]["traffic"]
        for user in data["users"]:
            writer.writerow(
                [
                    data["generated_at"], traffic["rx"], traffic["tx"], traffic["used"],
                    data["server"]["cpu"], data["server"]["memory"]["percent"],
                    user["username"], user["online"], user["upload"],
                    user["download"], user["total"],
                ]
            )
    state["last_history"] = now
    atomic_json(STATE_FILE, state)


def create_backup(force: bool = False) -> Optional[Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    backup = BACKUP_DIR / f"hy2-aio-backup-{day}.tar.gz"
    if force:
        backup = BACKUP_DIR / datetime.now(timezone.utc).strftime(
            "hy2-aio-backup-%Y-%m-%d-%H%M%S.tar.gz"
        )

    if force or not backup.exists():
        include = [
            "etc/hy2-aio",
            "etc/hysteria/config.yaml",
            "etc/hysteria/server.crt",
            "etc/hysteria/server.key",
            "etc/caddy/Caddyfile",
            "usr/local/lib/hy2-aio",
            "var/lib/hy2-aio/state.json",
            "var/www/hy2-aio/history.csv",
            "var/www/hy2-aio/users.csv",
            "root/hy2-aio-access.txt",
        ]
        temporary = Path(str(backup) + ".tmp")
        result = subprocess.run(
            ["tar", "-czf", str(temporary), "--ignore-failed-read", "-C", "/", *include],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0 and temporary.exists() and temporary.stat().st_size:
            os.replace(temporary, backup)
        elif temporary.exists():
            temporary.unlink()

    # Never publish backups under WEB_DIR — they contain TLS keys and secrets.
    stale_web_backup = DOWNLOAD_DIR / "hy2-aio-backup-latest.tar.gz"
    if stale_web_backup.exists():
        try:
            stale_web_backup.unlink()
        except OSError:
            pass

    cutoff = time.time() - int(load_env().get("BACKUP_RETENTION_DAYS", "14")) * 86400
    for path in BACKUP_DIR.glob("hy2-aio-backup-*.tar.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
    return backup if backup.exists() else None


def apply_web_permissions() -> None:
    for path in [DATA_FILE, USERS_CSV, HISTORY_CSV]:
        if path.exists():
            os.chmod(path, 0o640)
            try:
                shutil.chown(path, user="hy2-aio", group="caddy")
            except Exception:
                pass


def restart_hysteria() -> None:
    """Ask root path unit to restart hysteria-server (backend runs unprivileged)."""
    flag = Path("/run/hy2-aio/reload-hysteria")
    try:
        flag.unlink(missing_ok=True)
    except TypeError:
        if flag.exists():
            flag.unlink()
    except OSError:
        pass
    flag.write_text(str(time.time()), encoding="utf-8")
    for _ in range(75):
        time.sleep(0.2)
        if not flag.exists():
            return
    raise RuntimeError("等待 Hysteria 重启超时")


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")


def mutate_users(mutator) -> dict[str, Any]:
    """修改 users.json 并重建 Hysteria；失败时回滚。"""
    with LOCK:
        users = load_users()
        backup = json.dumps(users, ensure_ascii=False, indent=2)
        try:
            mutator(users)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(str(error) or "用户数据无效") from error
        try:
            atomic_json(USERS_FILE, users)
            result = subprocess.run(
                [str(REBUILD_FILE)], capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "rebuild_config.py 执行失败")
            restart_hysteria()
        except Exception:
            atomic_json(USERS_FILE, json.loads(backup))
            subprocess.run([str(REBUILD_FILE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                restart_hysteria()
            except Exception:
                pass
            raise
        os.chmod(USERS_FILE, 0o640)
        try:
            shutil.chown(USERS_FILE, user="hy2-aio", group="hy2-aio")
        except Exception:
            pass
        return collect()


def apply_user_change(username: str, update) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username not in users:
            raise ValueError("用户不存在")
        update(users[username])

    return mutate_users(mutator)


def add_user(username: str) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username in users:
            raise ValueError("用户已存在")
        users[username] = {
            "password": secrets.token_hex(16),
            "token": secrets.token_hex(24),
            "note": "",
            "disabled": False,
        }

    return mutate_users(mutator)


def remove_user(username: str) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username not in users:
            raise ValueError("用户不存在")
        if len(users) <= 1:
            raise ValueError("不能删除最后一个用户")
        del users[username]

    return mutate_users(mutator)


def rotate_user(username: str) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username not in users:
            raise ValueError("用户不存在")
        users[username]["password"] = secrets.token_hex(16)
        users[username]["token"] = secrets.token_hex(24)

    return mutate_users(mutator)


def subscription_for_token(token: str):
    for username, info in load_users().items():
        if str(info.get("token")) == token:
            return username, info
    return None, None


def user_credential_value(username: str, kind: str) -> str:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")
    if kind not in ("subscription", "direct", "password"):
        raise ValueError("未知凭据类型")
    users = load_users()
    if username not in users:
        raise ValueError("用户不存在")
    info = users[username]
    env = load_env()
    password = str(info["password"])
    token = str(info["token"])
    if kind == "password":
        return password
    if kind == "subscription":
        return f"{public_base_url(env)}/s/{token}"
    return direct_link(env, username, password)


RATE_BUCKETS: dict[str, list[float]] = {}
RATE_BUCKET_LOCK = threading.Lock()


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = str(handler.headers.get("X-Forwarded-For", "") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = str(handler.headers.get("X-Real-IP", "") or "").strip()
    if real:
        return real
    if handler.client_address:
        return str(handler.client_address[0])
    return "unknown"


def rate_limit_allow(bucket: str, ip: str, limit: int, window: float) -> bool:
    if limit <= 0:
        return True
    key = f"{bucket}:{ip}"
    now = time.time()
    with RATE_BUCKET_LOCK:
        hits = RATE_BUCKETS.setdefault(key, [])
        cutoff = now - window
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


def rate_limit_from_env(env: dict[str, str], key: str, default: int) -> int:
    try:
        return max(0, int(env.get(key, str(default)) or default))
    except ValueError:
        return default


class Handler(BaseHTTPRequestHandler):
    server_version = "HY2AIO/1.0"

    def log_message(self, format_string: str, *args: Any) -> None:
        return

    def require_api_secret(self) -> bool:
        expected = str(load_env().get("API_SECRET", "") or "")
        provided = str(self.headers.get("X-API-Secret", "") or "")
        expected_b = expected.encode("utf-8")
        provided_b = provided.encode("utf-8")
        if (
            not expected_b
            or len(provided_b) != len(expected_b)
            or not hmac.compare_digest(provided_b, expected_b)
        ):
            self.send_json(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def require_same_origin(self) -> bool:
        """Reject cross-site browser POSTs when Origin/Referer is present."""
        origin = str(self.headers.get("Origin", "") or "").strip()
        referer = str(self.headers.get("Referer", "") or "").strip()
        if not origin and not referer:
            return True
        env = load_env()
        domain = str(env.get("DOMAIN", "") or "").strip().lower()
        port = str(env.get("PANEL_PORT", "443") or "443").strip()
        if not domain:
            return True

        def host_ok(url: str) -> bool:
            try:
                parsed = urllib.parse.urlparse(url)
            except Exception:
                return False
            host = (parsed.hostname or "").lower()
            if host != domain:
                return False
            url_port = parsed.port
            if url_port is None:
                # Scheme default port: accept when panel uses standard ports,
                # or when Host already matched domain (custom-port pages still send :port).
                return True
            return str(url_port) == port

        if origin and origin.lower() != "null" and not host_ok(origin):
            print(f"[hy2-aio] forbidden origin got={origin!r} domain={domain!r} port={port!r}", flush=True)
            self.send_json(403, {"ok": False, "error": "forbidden origin"})
            return False
        if not origin and referer and not host_ok(referer):
            print(f"[hy2-aio] forbidden referer got={referer!r} domain={domain!r} port={port!r}", flush=True)
            self.send_json(403, {"ok": False, "error": "forbidden referer"})
            return False
        return True

    def require_rate_limit(self, bucket: str, env_key: str, default: int, window: float = 60.0) -> bool:
        env = load_env()
        limit = rate_limit_from_env(env, env_key, default)
        if rate_limit_allow(bucket, client_ip(self), limit, window):
            return True
        self.send_json(429, {"ok": False, "error": "请求过于频繁，请稍后再试"})
        return False

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_subscription(self, token: str) -> None:
        if not self.require_rate_limit("subscription", "RATE_LIMIT_SUBSCRIPTION", 30):
            return
        username, info = subscription_for_token(token)
        if username is None or info is None:
            self.send_error(404)
            return
        if info.get("disabled"):
            self.send_json(403, {"ok": False, "error": "账号已被禁用"})
            return
        try:
            env = load_env()
            body = subscription_yaml(env, username, str(info["password"]))
            # Clash traffic bar must match panel "整机套餐" (NIC counters), not per-user HY2.
            cached = read_json(DATA_FILE, {})
            traffic = cached.get("server", {}).get("traffic", {})
            if not isinstance(traffic, dict):
                traffic = {}
            rx = int(traffic.get("rx", 0) or 0)
            tx = int(traffic.get("tx", 0) or 0)
            limit = int(traffic.get("limit", 0) or 0) or int(env.get("TOTAL_BYTES", "0") or 0)
            if not limit:
                limit = int(env.get("TOTAL_BYTES", "0") or 0)
        except Exception as error:
            self.send_json(500, {"ok": False, "error": "订阅生成失败"})
            print(f"[hy2-aio] subscription error: {error}", flush=True)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/yaml; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="HY2-{username}.yaml"')
        self.send_header(
            "Subscription-Userinfo",
            f"upload={rx}; download={tx}; total={limit}; expire=0",
        )
        self.send_header("Profile-Update-Interval", "1")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self.send_json(200, {"ok": True, "time": iso_now()})
            return
        if path.startswith("/s/"):
            self.send_subscription(path[3:].strip("/") if path.startswith("/s/") else path.strip("/"))
            return
        self.send_error(404)

    def read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            raise ValueError("Content-Length 无效")
        if length < 0 or length > 65536:
            raise ValueError("请求体过大或无效")
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def handle_user_change(self, action: str, payload: dict[str, Any]) -> None:
        username = str(payload.get("username", "")).strip()
        try:
            if action == "note":
                note = str(payload.get("note", "")).strip()
                if len(note) > 100:
                    self.send_json(400, {"ok": False, "error": "备注最长 100 字符"})
                    return
                data = apply_user_change(username, lambda info: info.update({"note": note}))
            elif action == "disable":
                data = apply_user_change(username, lambda info: info.update({"disabled": True}))
            elif action == "enable":
                data = apply_user_change(username, lambda info: info.update({"disabled": False}))
            elif action == "add":
                data = add_user(username)
            elif action == "remove":
                data = remove_user(username)
            elif action == "rotate":
                data = rotate_user(username)
            else:
                self.send_error(404)
                return
        except ValueError as error:
            self.send_json(400, {"ok": False, "error": str(error)})
            return
        self.send_json(200, {"ok": True, "generated_at": data["generated_at"]})

    def handle_user_credentials(self, payload: dict[str, Any]) -> None:
        username = str(payload.get("username", ""))
        kind = str(payload.get("kind", "")).strip().lower()
        try:
            value = user_credential_value(username, kind)
        except ValueError as error:
            self.send_json(400, {"ok": False, "error": str(error)})
            return
        self.send_json(200, {"ok": True, "kind": kind, "value": value})

    def do_POST(self) -> None:
        if not self.require_api_secret():
            return
        if not self.require_same_origin():
            return
        if not self.require_rate_limit("api", "RATE_LIMIT_API", 120):
            return
        path = self.path.split("?", 1)[0]
        try:
            if path == "/sync":
                data = collect()
                self.send_json(200, {"ok": True, "generated_at": data["generated_at"]})
                return
            if path == "/backup":
                data = collect(force_backup=True)
                backup = create_backup(force=True)
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "generated_at": data["generated_at"],
                        "backup": str(backup) if backup else None,
                    },
                )
                return
            if path == "/user/credentials":
                self.handle_user_credentials(self.read_body())
                return
            if path in (
                "/user/note",
                "/user/disable",
                "/user/enable",
                "/user/add",
                "/user/remove",
                "/user/rotate",
            ):
                action = path[6:] if path.startswith("/user/") else path.lstrip("/")
                self.handle_user_change(action, self.read_body())
                return
        except Exception as error:
            self.send_json(500, {"ok": False, "error": "内部错误"})
            print(f"[hy2-aio] api error: {error}", flush=True)
            return
        self.send_error(404)


def collector_loop() -> None:
    failures = 0
    while True:
        try:
            collect()
            failures = 0
        except Exception as error:
            failures += 1
            print(f"[hy2-aio] collect failed ({failures}): {error}", flush=True)
        time.sleep(60)


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        collect()
    except Exception as error:
        print(f"[hy2-aio] initial collect failed: {error}", flush=True)
    threading.Thread(target=collector_loop, daemon=True).start()
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()


if __name__ == "__main__":
    main()
PY
  chmod 0755 "$APP_FILE"
}
