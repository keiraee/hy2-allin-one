#!/usr/bin/env bash
# backend.sh - 后端 Python 服务生成

write_backend() {
  cat > "$APP_FILE" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import csv
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import uuid
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
from typing import Any, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - production is Linux; keeps local Windows checks usable.
    fcntl = None

ENV_FILE = Path("/etc/hy2-aio/config.env")
USERS_FILE = Path("/etc/hy2-aio/users.json")
USER_MUTATION_LOCK = Path("/etc/hy2-aio/.users.lock")
MODE_FILE = Path("/etc/hy2-aio/client-mode.json")
HYSTERIA_CONFIG = Path("/etc/hysteria/config.yaml")
STATE_DIR = Path("/var/lib/hy2-aio")
STATE_FILE = STATE_DIR / "state.json"
APPLY_ERROR_FILE = STATE_DIR / "apply-error.txt"
BACKUP_DIR = STATE_DIR / "backups"
BACKUP_ROOT = Path("/")
BACKUP_REQUIRED_MEMBERS = (
    "etc/hy2-aio/config.env",
    "etc/hy2-aio/users.json",
    "etc/hy2-aio/client-mode.json",
    "etc/hy2-aio/xray.json",
    "etc/hysteria/config.yaml",
    "etc/hysteria/server.crt",
    "etc/hysteria/server.key",
    "etc/caddy/Caddyfile",
    "usr/local/lib/hy2-aio/server.py",
    "usr/local/lib/hy2-aio/rebuild_config.py",
    "usr/local/lib/hy2-aio/rebuild_xray.py",
)
BACKUP_OPTIONAL = (
    "etc/caddy/hy2-aio.caddy",
    "etc/hy2-aio/hy2.off",
    "etc/systemd/system/hysteria-server.service.d/hy2-switch.conf",
    "usr/local/lib/hy2-aio/hysteria-control.sh",
    "usr/local/lib/hy2-aio/xray-control.sh",
    "var/lib/hy2-aio/state.json",
    "var/www/hy2-aio/history.csv",
    "var/www/hy2-aio/users.csv",
)
REBUILD_FILE = Path("/usr/local/lib/hy2-aio/rebuild_config.py")
XRAY_REBUILD_FILE = Path("/usr/local/lib/hy2-aio/rebuild_xray.py")
XRAY_CONFIG = Path("/etc/hy2-aio/xray.json")
HY2_OFF_FILE = Path("/etc/hy2-aio/hy2.off")
HYSTERIA_CMD_FILE = Path("/run/hy2-aio/hysteria-cmd")
HYSTERIA_RELOAD_FLAG = Path("/run/hy2-aio/reload-hysteria")
XRAY_CMD_FILE = Path("/run/hy2-aio/xray-cmd")
XRAY_RELOAD_FLAG = Path("/run/hy2-aio/reload-xray")
WEB_DIR = Path("/var/www/hy2-aio")
DOWNLOAD_DIR = WEB_DIR / "downloads"
DATA_FILE = WEB_DIR / "data.json"
USERS_CSV = WEB_DIR / "users.csv"
HISTORY_CSV = WEB_DIR / "history.csv"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 18081
LISTEN = (BACKEND_HOST, BACKEND_PORT)
LOCK = threading.RLock()
BACKUP_LOCK = threading.Lock()
BACKUP_VALIDATED: dict[Path, tuple[int, int]] = {}
LAST_BACKUP_ERROR: Optional[str] = None
BACKUP_RETRY_AFTER = 0.0


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


def user_is_disabled(info: dict[str, Any]) -> bool:
    value = info.get("disabled", False)
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def has_enabled_users(users: Optional[dict[str, Any]] = None) -> bool:
    if users is None:
        users = load_users()
    for info in users.values():
        if isinstance(info, dict) and not user_is_disabled(info):
            return True
    return False


def hy2_is_off() -> bool:
    return HY2_OFF_FILE.exists()


def set_hy2_off() -> None:
    HY2_OFF_FILE.write_text("1\n", encoding="utf-8")
    try:
        os.chmod(HY2_OFF_FILE, 0o640)
    except OSError:
        pass


def set_hy2_on() -> None:
    try:
        HY2_OFF_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


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
    if not math.isfinite(up) or not math.isfinite(down) or up <= 0 or down <= 0:
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    if up > 2000 or down > 2000:
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


def atomic_bytes(path: Path, data: bytes, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, data: Any) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_bytes(path, content)


@contextmanager
def user_mutation_lock():
    """Coordinate panel mutations with root CLI processes."""
    USER_MUTATION_LOCK.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(USER_MUTATION_LOCK, os.O_CREAT | os.O_RDWR, 0o660)
    try:
        os.chmod(USER_MUTATION_LOCK, 0o660)
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def assert_writable_dir(path: Path, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".hy2-write-probe-{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        hint = ""
        if path == Path("/etc/hy2-aio"):
            hint = "；请执行：chown root:hy2-aio /etc/hy2-aio && chmod 0770 /etc/hy2-aio"
        elif path == Path("/etc/hysteria"):
            hint = "；请执行：chown hysteria:hysteria /etc/hysteria && chmod 2770 /etc/hysteria && chmod 0660 /etc/hysteria/config.yaml"
        raise PermissionError(f"{label} 不可写：{path} ({error}){hint}") from error


def check_runtime_permissions() -> None:
    """Fail fast with a clear log if panel mutations cannot write required dirs."""
    assert_writable_dir(STATE_DIR, "状态目录")
    assert_writable_dir(BACKUP_DIR, "备份目录")
    assert_writable_dir(WEB_DIR, "面板目录")
    assert_writable_dir(DOWNLOAD_DIR, "下载目录")
    assert_writable_dir(Path("/run/hy2-aio"), "运行时目录")
    assert_writable_dir(USERS_FILE.parent, "配置目录")
    assert_writable_dir(Path("/etc/hysteria"), "Hysteria 配置目录")
    print("[hy2-aio] runtime write paths OK", flush=True)


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


def counter_delta(current: int, last: int) -> int:
    current = max(int(current or 0), 0)
    last = max(int(last or 0), 0)
    if current >= last:
        return current - last
    return current


def accumulate_user_traffic(user_state: dict[str, Any], raw: dict[str, Any]) -> tuple[int, int]:
    raw_tx = int(raw.get("tx", 0) or 0)
    raw_rx = int(raw.get("rx", 0) or 0)
    tx = counter_delta(raw_tx, int(user_state.get("last_tx", 0) or 0))
    rx = counter_delta(raw_rx, int(user_state.get("last_rx", 0) or 0))
    user_state["last_tx"] = raw_tx
    user_state["last_rx"] = raw_rx
    user_state["month_tx"] = int(user_state.get("month_tx", 0)) + tx
    user_state["month_rx"] = int(user_state.get("month_rx", 0)) + rx
    user_state["lifetime_tx"] = int(user_state.get("lifetime_tx", 0)) + tx
    user_state["lifetime_rx"] = int(user_state.get("lifetime_rx", 0)) + rx
    return tx, rx


def is_transient_hysteria_error(error: BaseException) -> bool:
    if isinstance(error, (ConnectionRefusedError, ConnectionResetError, TimeoutError)):
        return True
    if isinstance(error, OSError) and getattr(error, "errno", None) in {111, 61, 104, 110}:
        return True
    reason = getattr(error, "reason", None)
    if reason is not None and reason is not error:
        return is_transient_hysteria_error(reason)
    text = str(error).lower()
    return "connection refused" in text or "timed out" in text or "temporarily unavailable" in text


def hysteria_api(path: str, secret: str, *, attempts: int = 10, delay: float = 0.3) -> Any:
    stats_port = load_env().get("STATS_PORT", "9999")
    url = f"http://127.0.0.1:{stats_port}" + path
    last_error: Optional[BaseException] = None
    for attempt in range(max(attempts, 1)):
        request = urllib.request.Request(
            url,
            headers={"Authorization": secret, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)
        except Exception as error:
            last_error = error
            if attempt + 1 >= attempts or not is_transient_hysteria_error(error):
                raise
            time.sleep(delay)
    raise last_error or RuntimeError(f"Hysteria API 失败：{path}")


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


def obfs_enabled(env: dict[str, str]) -> bool:
    raw = str(env.get("OBFS_ENABLED", "true")).strip().lower()
    return raw in ("1", "true", "yes", "on")


def public_base_url(env: dict[str, str]) -> str:
    """Panel/subscription base URL (always HTTPS)."""
    domain = str(env.get("DOMAIN", "") or "")
    port = str(env.get("PANEL_PORT", "443") or "443")
    if port in ("443", ""):
        return f"https://{domain}"
    return f"https://{domain}:{port}"


def direct_link(env: dict[str, str], username: str, password: str) -> str:
    auth = urllib.parse.quote(f"{username}:{password}", safe="")
    query_items: dict[str, str] = {
        "sni": env.get("SNI", "www.amazon.sg"),
    }
    if obfs_enabled(env):
        query_items["obfs"] = "salamander"
        query_items["obfs-password"] = env["OBFS_PASSWORD"]
    if client_insecure(env):
        query_items["insecure"] = "1"
    query = urllib.parse.urlencode(query_items)
    name = urllib.parse.quote(f"HY2-{username}", safe="")
    return f"hysteria2://{auth}@{env['PUBLIC_IP']}:{env.get('HY2_PORT', '443')}/?{query}#{name}"


def xray_port(env: dict[str, str]) -> str:
    raw = str(env.get("XRAY_PORT") or "").strip()
    if raw:
        return raw
    hy2 = str(env.get("HY2_PORT") or "8443")
    panel = str(env.get("PANEL_PORT") or "443")
    if hy2 != panel:
        return hy2
    if panel != "8443":
        return "8443"
    return "443"


def reality_dest(env: dict[str, str]) -> str:
    return str(env.get("REALITY_DEST") or "www.cloudflare.com:443").strip() or "www.cloudflare.com:443"


def reality_server_name(env: dict[str, str]) -> str:
    names = str(env.get("REALITY_SERVER_NAMES") or "").strip()
    if names:
        return names.split(",")[0].strip()
    dest = reality_dest(env)
    return dest.rsplit(":", 1)[0]


def new_vless_id() -> str:
    return str(uuid.uuid4())


VLESS_NODE_NAME = "hy2超时备用临时节点"


def vless_link(env: dict[str, str], username: str, info: Optional[dict[str, Any]] = None) -> str:
    payload = info if isinstance(info, dict) else {}
    vless_id = str(payload.get("vless_id") or "").strip()
    public_key = str(env.get("REALITY_PUBLIC_KEY") or "").strip()
    short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
    if not (vless_id and public_key and short_id):
        return ""
    query = urllib.parse.urlencode(
        {
            "encryption": "none",
            "flow": "xtls-rprx-vision",
            "security": "reality",
            "sni": reality_server_name(env),
            "fp": "chrome",
            "pbk": public_key,
            "sid": short_id,
            "type": "tcp",
        }
    )
    name = urllib.parse.quote(VLESS_NODE_NAME, safe="")
    return f"vless://{vless_id}@{env['PUBLIC_IP']}:{xray_port(env)}?{query}#{name}"


def direct_links(env: dict[str, str], username: str, password: str, info: Optional[dict[str, Any]] = None) -> str:
    lines = [direct_link(env, username, password)]
    extra = vless_link(env, username, info)
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def subscription_yaml(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
) -> bytes:
    def q(value: str) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    mode = mode_for_user(username)
    rate_lines = ""
    if mode.get("mode") == "brutal":
        rate_lines = (
            f'    up: "{float(mode["up_mbps"]):g} Mbps"\n'
            f'    down: "{float(mode["down_mbps"]):g} Mbps"\n'
        )

    obfs_lines = ""
    if obfs_enabled(env):
        obfs_lines = (
            "    obfs: salamander\n"
            f"    obfs-password: {q(env['OBFS_PASSWORD'])}\n"
        )

    node = q("HY2-" + username)
    vless_block = ""
    vless_group = ""
    payload = info if isinstance(info, dict) else {}
    vless_id = str(payload.get("vless_id") or "").strip()
    public_key = str(env.get("REALITY_PUBLIC_KEY") or "").strip()
    short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
    if vless_id and public_key and short_id:
        vless_name = q(VLESS_NODE_NAME)
        vless_group = f"      - {vless_name}\n"
        vless_block = (
            f"  - name: {vless_name}\n"
            "    type: vless\n"
            f"    server: {q(env['PUBLIC_IP'])}\n"
            f"    port: {xray_port(env)}\n"
            f"    uuid: {q(vless_id)}\n"
            "    network: tcp\n"
            "    tls: true\n"
            "    udp: true\n"
            "    flow: xtls-rprx-vision\n"
            f"    servername: {q(reality_server_name(env))}\n"
            "    client-fingerprint: chrome\n"
            "    reality-opts:\n"
            f"      public-key: {q(public_key)}\n"
            f"      short-id: {q(short_id)}\n"
        )
    content = f"""mixed-port: 7890
allow-lan: false
mode: rule
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

proxies:
  - name: {node}
    type: hysteria2
    server: {q(env["PUBLIC_IP"])}
    port: {env.get('HY2_PORT', '443')}
{rate_lines}    password: {q(username + ":" + password)}
{obfs_lines}    sni: {q(env.get("SNI", "www.amazon.sg"))}
    skip-cert-verify: {"true" if client_insecure(env) else "false"}
    udp: true
    keepalive: 5s
{vless_block}
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - {node}
{vless_group}      - DIRECT

rule-providers:
  china-domain:
    type: http
    behavior: domain
    format: yaml
    path: ./ruleset/china-domain.yaml
    interval: 86400
    url: https://testingcf.jsdelivr.net/gh/blackmatrix7/ios_rule_script@master/rule/Clash/China/China_Domain.yaml
  china-ip:
    type: http
    behavior: ipcidr
    format: mrs
    path: ./ruleset/china-ip.mrs
    interval: 86400
    url: https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geoip/cn.mrs

rules:
  - DOMAIN-SUFFIX,lan,DIRECT
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - RULE-SET,china-domain,DIRECT
  - RULE-SET,china-ip,DIRECT
  - MATCH,PROXY
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


def collect(run_backup: bool = True) -> dict[str, Any]:
    global LAST_BACKUP_ERROR, BACKUP_RETRY_AFTER
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
        hy2_enabled = not hy2_is_off()
        traffic: dict[str, Any] = {}
        online: dict[str, Any] = {}
        stream_dump: list[Any] = []
        if hy2_enabled:
            try:
                # Snapshot only. Clearing here would drop bytes if we crash before persist.
                payload = hysteria_api("/traffic", env["API_SECRET"])
                traffic = payload if isinstance(payload, dict) else {}
            except Exception as error:
                traffic = {}
                errors.append(f"traffic API: {error}")

            try:
                payload = hysteria_api("/online", env["API_SECRET"])
                online = payload if isinstance(payload, dict) else {}
            except Exception as error:
                online = {}
                errors.append(f"online API: {error}")

            try:
                stream_dump = normalize_streams_payload(
                    hysteria_api("/dump/streams", env["API_SECRET"], attempts=2, delay=0.2)
                )
            except Exception:
                stream_dump = []

        state_users = state.setdefault("users", {})
        output_users: list[dict[str, Any]] = []
        timestamp = iso_now()
        remember_user_streams(state, stream_dump, timestamp)
        log_lines = hysteria_connect_log_lines()
        remember_client_ips(state, stream_dump, log_lines, timestamp)
        remember_log_destinations(state, log_lines, timestamp)

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
            raw = traffic.get(username)
            raw = raw if isinstance(raw, dict) else None
            if raw is not None:
                tx, rx = accumulate_user_traffic(user_state, raw)
            else:
                tx = rx = 0
            devices = int(online.get(username, 0) or 0)
            if tx or rx or devices:
                user_state["last_active"] = timestamp

            client_mode = mode_for_user(username, modes)
            recent_ips = client_ips_for_user(state, username)
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
                    "client_ip": recent_ips[0]["ip"] if recent_ips else "",
                    "mode": mode_label(client_mode),
                }
            )

        for stale in [name for name in list(state_users) if name not in users]:
            state_users.pop(stale, None)

        apply_error = read_apply_error()
        if apply_error:
            errors.append(apply_error)

        stored_modes = read_json(MODE_FILE, {})
        if isinstance(stored_modes, dict) and isinstance(stored_modes.get("users"), dict):
            leftover_modes = [name for name in stored_modes["users"] if name not in users]
            if leftover_modes:
                for name in leftover_modes:
                    stored_modes["users"].pop(name, None)
                atomic_json(MODE_FILE, stored_modes)

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
                    "Hysteria": (
                        "off" if not hy2_enabled else service_status("hysteria-server.service")
                    ),
                    "Xray": service_status("hy2-xray.service"),
                    "HY2 AIO": service_status("hy2-aio.service"),
                    "Caddy": service_status("caddy.service"),
                },
                "hy2_enabled": hy2_enabled,
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
        if run_backup:
            now = time.time()
            if now >= BACKUP_RETRY_AFTER:
                try:
                    create_backup()
                    LAST_BACKUP_ERROR = None
                    BACKUP_RETRY_AFTER = 0.0
                except RuntimeError as error:
                    LAST_BACKUP_ERROR = str(error)
                    BACKUP_RETRY_AFTER = now + 3600
                    print(f"[hy2-aio] automatic backup failed: {error}", flush=True)
            if LAST_BACKUP_ERROR:
                errors.append(f"backup: {LAST_BACKUP_ERROR}")
                data["errors"] = errors
                atomic_json(DATA_FILE, data)
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


def tar_error_message(stderr: str, returncode: int) -> str:
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    useful = [line for line in lines if "Exiting with failure status" not in line]
    chosen = useful[-3:] if useful else lines[-2:]
    if chosen:
        return "；".join(chosen)
    return f"tar 退出码 {returncode}"


def backup_member_readable(relative: str) -> bool:
    path = BACKUP_ROOT / relative
    try:
        return path.is_file() and os.access(path, os.R_OK)
    except OSError:
        return False


def backup_include_list() -> list[str]:
    missing = [
        relative for relative in BACKUP_REQUIRED_MEMBERS
        if not (BACKUP_ROOT / relative).exists()
    ]
    if missing:
        raise RuntimeError(f"备份缺少必需路径：{', '.join(missing)}")
    unreadable = [
        relative for relative in BACKUP_REQUIRED_MEMBERS
        if not backup_member_readable(relative)
    ]
    if unreadable:
        raise RuntimeError(f"备份无法读取必需文件：{', '.join(unreadable)}")
    include = list(BACKUP_REQUIRED_MEMBERS)
    include.extend(
        relative for relative in BACKUP_OPTIONAL
        if backup_member_readable(relative)
    )
    return include


def validate_backup_archive(path: Path) -> None:
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = {member.name.rstrip("/"): member for member in archive.getmembers()}
    except (OSError, tarfile.TarError) as error:
        raise RuntimeError(f"备份归档无法读取：{error}") from error

    missing = [relative for relative in BACKUP_REQUIRED_MEMBERS if relative not in members]
    empty = [
        relative
        for relative in BACKUP_REQUIRED_MEMBERS
        if relative in members and members[relative].isfile() and members[relative].size == 0
    ]
    if missing or empty:
        details = []
        if missing:
            details.append(f"缺少 {', '.join(missing)}")
        if empty:
            details.append(f"空文件 {', '.join(empty)}")
        raise RuntimeError(f"备份完整性校验失败：{'; '.join(details)}")


def create_backup(force: bool = False) -> Optional[Path]:
    with BACKUP_LOCK:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        backup = BACKUP_DIR / f"hy2-aio-backup-{day}.tar.gz"
        if force:
            backup = BACKUP_DIR / datetime.now(timezone.utc).strftime(
                "hy2-aio-backup-%Y-%m-%d-%H%M%S-%f.tar.gz"
            )

        create = force or not backup.exists()
        if not create:
            stat = backup.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size)
            if BACKUP_VALIDATED.get(backup) != fingerprint:
                try:
                    validate_backup_archive(backup)
                    BACKUP_VALIDATED[backup] = fingerprint
                except RuntimeError:
                    backup.unlink()
                    BACKUP_VALIDATED.pop(backup, None)
                    create = True

        if create:
            include = backup_include_list()
            temporary = Path(str(backup) + ".tmp")
            try:
                result = subprocess.run(
                    ["tar", "-czf", str(temporary), "-C", str(BACKUP_ROOT), *include],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    message = tar_error_message(result.stderr, result.returncode)
                    archive_ok = (
                        result.returncode == 1
                        and temporary.exists()
                        and temporary.stat().st_size > 0
                    )
                    if archive_ok:
                        try:
                            validate_backup_archive(temporary)
                        except RuntimeError as error:
                            raise RuntimeError(f"备份创建失败：{message}") from error
                    else:
                        raise RuntimeError(f"备份创建失败：{message}")
                if not temporary.exists() or temporary.stat().st_size == 0:
                    raise RuntimeError("备份创建失败：未生成有效归档")
                validate_backup_archive(temporary)
                os.chmod(temporary, 0o600)
                os.replace(temporary, backup)
                stat = backup.stat()
                BACKUP_VALIDATED[backup] = (stat.st_mtime_ns, stat.st_size)
            except Exception:
                if temporary.exists():
                    temporary.unlink()
                raise

        # Never publish backups under WEB_DIR — they contain TLS keys and secrets.
        stale_web_backup = DOWNLOAD_DIR / "hy2-aio-backup-latest.tar.gz"
        if stale_web_backup.exists():
            try:
                stale_web_backup.unlink()
            except OSError:
                pass

        cutoff = time.time() - backup_retention_days() * 86400
        for path in BACKUP_DIR.glob("hy2-aio-backup-*.tar.gz"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                BACKUP_VALIDATED.pop(path, None)
        return backup


def backup_retention_days() -> int:
    raw = str(load_env().get("BACKUP_RETENTION_DAYS", "14") or "14").strip()
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = 14
    return max(1, min(days, 3650))


def apply_web_permissions() -> None:
    for path in [DATA_FILE, USERS_CSV, HISTORY_CSV]:
        if path.exists():
            os.chmod(path, 0o640)
            try:
                shutil.chown(path, user="hy2-aio", group="caddy")
            except Exception:
                pass


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def request_hysteria(action: str) -> None:
    """Ask root path unit to stop/start/restart hysteria-server (backend is unprivileged)."""
    if action not in ("stop", "start", "restart"):
        raise ValueError(f"未知 Hysteria 操作：{action}")
    _unlink_quiet(HYSTERIA_RELOAD_FLAG)
    HYSTERIA_CMD_FILE.write_text(action + "\n", encoding="utf-8")
    HYSTERIA_RELOAD_FLAG.write_text(str(time.time()), encoding="utf-8")
    for _ in range(75):
        time.sleep(0.2)
        if not HYSTERIA_RELOAD_FLAG.exists():
            return
    raise RuntimeError("等待 Hysteria 操作超时")


def request_xray(action: str) -> None:
    """Ask root path unit to stop/start/restart hy2-xray (backend is unprivileged)."""
    if action not in ("stop", "start", "restart"):
        raise ValueError(f"未知 Xray 操作：{action}")
    _unlink_quiet(XRAY_RELOAD_FLAG)
    XRAY_CMD_FILE.write_text(action + "\n", encoding="utf-8")
    XRAY_RELOAD_FLAG.write_text(str(time.time()), encoding="utf-8")
    for _ in range(75):
        time.sleep(0.2)
        if not XRAY_RELOAD_FLAG.exists():
            return
    raise RuntimeError("等待 Xray 操作超时")


def restart_hysteria() -> None:
    request_hysteria("restart")


def xray_rebuild_available() -> bool:
    return XRAY_REBUILD_FILE.exists()


def rebuild_xray_config() -> None:
    if not xray_rebuild_available():
        return
    result = subprocess.run(
        [str(XRAY_REBUILD_FILE)], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "rebuild_xray.py 执行失败")


def apply_xray_after_users(users: dict[str, Any]) -> None:
    if not xray_rebuild_available():
        return
    if not has_enabled_users(users):
        request_xray("stop")
        return
    request_xray("restart")


def apply_hysteria_after_users(users: dict[str, Any]) -> None:
    if not has_enabled_users(users):
        set_hy2_off()
        request_hysteria("stop")
        return
    if hy2_is_off():
        return
    restart_hysteria()


def hy2_turn_off() -> dict[str, Any]:
    set_hy2_off()
    request_hysteria("stop")
    return collect()


def hy2_turn_on() -> dict[str, Any]:
    users = load_users()
    if not has_enabled_users(users):
        raise ValueError("请先启用至少一个用户")
    set_hy2_on()
    try:
        result = subprocess.run(
            [str(REBUILD_FILE)], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "rebuild_config.py 执行失败")
    except Exception:
        set_hy2_off()
        raise
    request_hysteria("start")
    return collect()


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")
TRAFFIC_HISTORY_DAYS = 7
DEST_MAX_PER_USER = 80
CLIENT_IP_MAX = 8
CLIENT_ADDR_KEYS = ("addr", "client_addr", "remote_addr", "src_addr")
LOG_ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)


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


def session_stats_from_logs(log_lines: list[str], username: str) -> dict[str, Any]:
    opens: dict[str, datetime] = {}
    durations: list[int] = []
    last_by_ip: dict[str, int] = {}
    for line in log_lines or []:
        text = str(line or "")
        lowered = text.lower()
        if "tcp error" in lowered and "client connected" not in lowered:
            continue
        parsed = parse_hysteria_connect_line(text)
        if not parsed or parsed[0] != username:
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
    state: dict[str, Any], log_lines: list[str], timestamp: str
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
        user = str(obj.get("id") or "").strip()
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
        apply_seen_time(item, stamp_from_log_line(text, timestamp))
        key = (user, host)
        if key not in created:
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
) -> None:
    if not isinstance(state, dict):
        return
    if not isinstance(streams, list):
        streams = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        user = str(stream.get("auth") or "").strip()
        addr = stream_client_addr(stream)
        if user and addr:
            record_client_ip(state, user, addr, timestamp)
    for line in log_lines or []:
        parsed = parse_hysteria_connect_line(str(line))
        if not parsed:
            continue
        record_client_ip(state, parsed[0], parsed[1], timestamp)
    prune_client_ips(state)


def client_ips_for_user(state: Any, username: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    bucket: dict[str, Any] = {}
    if isinstance(state, dict):
        stored = state.get("client_ips")
        if isinstance(stored, dict) and isinstance(stored.get(username), dict):
            bucket = stored[username]
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
    state: dict[str, Any], streams: list[Any], timestamp: str
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
        user = str(stream.get("auth") or "").strip()
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


def live_streams_for_user(username: str) -> list[dict[str, Any]]:
    if hy2_is_off():
        return []
    try:
        env = load_env()
        payload = hysteria_api(
            "/dump/streams", env.get("API_SECRET", ""), attempts=1, delay=0.1
        )
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for stream in normalize_streams_payload(payload):
        if str(stream.get("auth") or "").strip() != username:
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


def sites_for_user(username: str) -> list[dict[str, Any]]:
    state = read_json(STATE_FILE, {})
    bucket: dict[str, Any] = {}
    if isinstance(state, dict):
        dest = state.get("destinations")
        if isinstance(dest, dict) and isinstance(dest.get(username), dict):
            bucket = dest[username]
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


def history_files() -> list[Path]:
    files: list[Path] = []
    rotated = HISTORY_CSV.with_name("history.csv.1")
    if rotated.exists():
        files.append(rotated)
    if HISTORY_CSV.exists():
        files.append(HISTORY_CSV)
    return files


def load_user_history_rows(username: str) -> list[tuple[datetime, int, int]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRAFFIC_HISTORY_DAYS)
    rows: list[tuple[datetime, int, int]] = []
    for path in history_files():
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


def user_traffic_analysis(username: str) -> dict[str, Any]:
    username = str(username or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")
    users = load_users()
    if username not in users:
        raise ValueError("用户不存在")

    data = read_json(DATA_FILE, {})
    snapshot: dict[str, Any] = {}
    traffic: dict[str, Any] = {}
    if isinstance(data, dict):
        for item in data.get("users") or []:
            if isinstance(item, dict) and str(item.get("username", "")) == username:
                snapshot = item
                break
        server = data.get("server")
        if isinstance(server, dict) and isinstance(server.get("traffic"), dict):
            traffic = server["traffic"]

    upload = int(snapshot.get("upload", 0) or 0)
    download = int(snapshot.get("download", 0) or 0)
    total = int(snapshot.get("total", upload + download) or (upload + download))
    lifetime = int(snapshot.get("lifetime_total", 0) or 0)
    used = int(traffic.get("used", 0) or 0)
    share = round(total / used * 100, 1) if used else 0.0
    egress = ""
    if isinstance(data, dict) and isinstance(data.get("server"), dict):
        egress = str(data["server"].get("ip") or "")
    if not egress:
        try:
            egress = str(load_env().get("PUBLIC_IP", "") or "")
        except Exception:
            egress = ""
    series = series_from_history(load_user_history_rows(username))
    live = live_streams_for_user(username)
    stored_state = read_json(STATE_FILE, {})
    client_ips = client_ips_for_user(stored_state, username)
    seen_ips = {item["ip"] for item in client_ips}
    for row in live:
        ip = str(row.get("client") or "")
        if ip and ip not in seen_ips:
            client_ips.insert(
                0,
                {
                    "ip": ip,
                    "port": str(row.get("client_port") or ""),
                    "last_seen": str(row.get("last_active") or ""),
                },
            )
            seen_ips.add(ip)
    if len(client_ips) == 1:
        fallback = client_ips[0]
        for row in live:
            if not row.get("client"):
                row["client"] = fallback["ip"]
                row["client_port"] = fallback.get("port") or ""
    sessions = session_stats_from_logs(hysteria_connect_log_lines(), username)
    by_ip = sessions.pop("by_ip", {}) if isinstance(sessions, dict) else {}
    if isinstance(by_ip, dict):
        for item in client_ips:
            seconds = by_ip.get(item["ip"])
            if seconds:
                item["session_seconds"] = int(seconds)
    peak: Optional[dict[str, Any]] = None
    for item in series:
        delta_total = int(item["up"]) + int(item["down"])
        if peak is None or delta_total > int(peak["total"]):
            peak = {
                "t": item["t"],
                "up": item["up"],
                "down": item["down"],
                "total": delta_total,
            }
    return {
        "username": username,
        "month": {
            "upload": upload,
            "download": download,
            "total": total,
            "lifetime_total": lifetime,
            "share_percent": share,
        },
        "series": series,
        "has_history": bool(series),
        "peak": peak,
        "egress_ip": egress,
        "client_ips": client_ips[:CLIENT_IP_MAX],
        "live": live,
        "sites": sites_for_user(username),
        "online": int(snapshot.get("online", 0) or 0),
        "last_active": str(snapshot.get("last_active") or ""),
        "sessions": sessions,
    }


def forget_user_side_state(username: str) -> None:
    modes = read_json(MODE_FILE, {})
    if isinstance(modes, dict) and isinstance(modes.get("users"), dict):
        if username in modes["users"]:
            modes["users"].pop(username, None)
            atomic_json(MODE_FILE, modes)
            try:
                os.chmod(MODE_FILE, 0o640)
            except OSError:
                pass
    if STATE_FILE.exists():
        state = read_json(STATE_FILE, {})
        users_state = state.get("users")
        if isinstance(users_state, dict) and username in users_state:
            users_state.pop(username, None)
        destinations = state.get("destinations")
        if isinstance(destinations, dict) and username in destinations:
            destinations.pop(username, None)
        client_ips = state.get("client_ips")
        if isinstance(client_ips, dict) and username in client_ips:
            client_ips.pop(username, None)
        stream_bytes = state.get("stream_bytes")
        if isinstance(stream_bytes, dict):
            prefix = username + ":"
            for key in [item for item in list(stream_bytes) if str(item).startswith(prefix)]:
                stream_bytes.pop(key, None)
        atomic_json(STATE_FILE, state)


def users_fingerprint(users: dict[str, Any]) -> str:
    return json.dumps(users, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def publish_users_to_panel(users: dict[str, Any], timestamp: str) -> None:
    """把 users.json 立刻写进 data.json，避免面板还要等一次全量采集。"""
    if not DATA_FILE.exists():
        return
    try:
        data = read_json(DATA_FILE, {})
    except Exception:
        return
    if not isinstance(data, dict):
        data = {}
    existing: dict[str, dict[str, Any]] = {}
    raw_users = data.get("users")
    if isinstance(raw_users, list):
        for item in raw_users:
            if isinstance(item, dict) and item.get("username"):
                existing[str(item["username"])] = item
    output: list[dict[str, Any]] = []
    for username, info in sorted(users.items()):
        if not isinstance(info, dict):
            info = {}
        prev = existing.get(username, {})
        kept = username in existing
        upload = int(prev.get("upload") or 0) if kept else 0
        download = int(prev.get("download") or 0) if kept else 0
        output.append(
            {
                "username": username,
                "note": str(info.get("note", "") or ""),
                "disabled": bool(info.get("disabled", False)),
                "online": int(prev.get("online") or 0) if kept else 0,
                "upload": upload,
                "download": download,
                "total": upload + download,
                "lifetime_total": int(prev.get("lifetime_total") or 0) if kept else 0,
                "last_active": str(prev.get("last_active") or "从未") if kept else "从未",
                "client_ip": str(prev.get("client_ip") or "") if kept else "",
                "mode": str(prev.get("mode") or "BBR 自动估速") if kept else "BBR 自动估速",
            }
        )
    data["users"] = output
    data["generated_at"] = timestamp
    server = data.get("server")
    if not isinstance(server, dict):
        server = {}
        data["server"] = server
    server["hy2_enabled"] = not hy2_is_off()
    summary = data.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        data["summary"] = summary
    summary["users"] = len(output)
    summary["online_users"] = sum(1 for item in output if item.get("online"))
    summary["devices"] = sum(int(item.get("online") or 0) for item in output)
    try:
        atomic_json(DATA_FILE, data)
        apply_web_permissions()
    except Exception as error:
        print(f"[hy2-aio] panel user sync failed: {error}", flush=True)


def mutation_snapshot(users: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_now()
    publish_users_to_panel(users, timestamp)
    return {
        "generated_at": timestamp,
        "server": {"hy2_enabled": not hy2_is_off()},
    }


def _collect_after_mutation() -> None:
    try:
        collect(run_backup=False)
    except Exception as error:
        print(f"[hy2-aio] post-mutation collect failed: {error}", flush=True)


def schedule_collect() -> None:
    threading.Thread(
        target=_collect_after_mutation,
        daemon=True,
        name="hy2-aio-collect",
    ).start()


def read_apply_error() -> str:
    try:
        return APPLY_ERROR_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def set_apply_error(message: str = "") -> None:
    try:
        APPLY_ERROR_FILE.parent.mkdir(parents=True, exist_ok=True)
        if message:
            APPLY_ERROR_FILE.write_text(message.strip() + "\n", encoding="utf-8")
            return
        if APPLY_ERROR_FILE.exists():
            APPLY_ERROR_FILE.unlink()
    except OSError as error:
        print(f"[hy2-aio] apply error file failed: {error}", flush=True)


APPLY_LOCK = threading.Lock()


def _apply_services() -> None:
    last_error: Optional[BaseException] = None
    for attempt in range(1, 4):
        try:
            current = load_users()
            apply_hysteria_after_users(current)
            apply_xray_after_users(current)
            set_apply_error("")
            return
        except Exception as error:
            last_error = error
            print(
                f"[hy2-aio] post-mutation service apply failed ({attempt}/3): {error}",
                flush=True,
            )
            if attempt < 3:
                time.sleep(1)
    raise RuntimeError(str(last_error) if last_error else "内核重启失败")


def _apply_and_collect() -> None:
    """按磁盘上的最新用户表重启内核，再采集。不回滚已提交的 users.json。"""
    with APPLY_LOCK:
        try:
            _apply_services()
        except Exception as error:
            set_apply_error(f"用户已保存，但内核未加载最新配置：{error}")
            print(f"[hy2-aio] post-mutation service apply gave up: {error}", flush=True)
        _collect_after_mutation()


def schedule_apply_and_collect() -> None:
    threading.Thread(
        target=_apply_and_collect,
        daemon=True,
        name="hy2-aio-apply",
    ).start()


def mutate_users(mutator, apply_hysteria: bool = True) -> dict[str, Any]:
    """修改 users.json；认证相关变更才重建配置。立刻回面板，内核重启由调用方在 HTTP 200 之后调度。"""
    with LOCK, user_mutation_lock():
        users = load_users()
        users_backup = USERS_FILE.read_bytes()
        users_mode = USERS_FILE.stat().st_mode & 0o777
        config_backup = HYSTERIA_CONFIG.read_bytes()
        config_mode = HYSTERIA_CONFIG.stat().st_mode & 0o777
        xray_existed = XRAY_CONFIG.exists()
        xray_backup = XRAY_CONFIG.read_bytes() if xray_existed else None
        xray_mode = XRAY_CONFIG.stat().st_mode & 0o777 if xray_existed else 0o640
        was_off = hy2_is_off()
        before = users_fingerprint(users)
        try:
            mutator(users)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(str(error) or "用户数据无效") from error
        if users_fingerprint(users) == before:
            return mutation_snapshot(users)
        try:
            atomic_json(USERS_FILE, users)
            if apply_hysteria:
                result = subprocess.run(
                    [str(REBUILD_FILE)], capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "rebuild_config.py 执行失败")
                rebuild_xray_config()
                if not has_enabled_users(users):
                    set_hy2_off()
        except Exception:
            atomic_bytes(USERS_FILE, users_backup, users_mode)
            if apply_hysteria:
                atomic_bytes(HYSTERIA_CONFIG, config_backup, config_mode)
                if xray_existed and xray_backup is not None:
                    atomic_bytes(XRAY_CONFIG, xray_backup, xray_mode)
                elif XRAY_CONFIG.exists() and not xray_existed:
                    _unlink_quiet(XRAY_CONFIG)
                try:
                    if was_off:
                        set_hy2_off()
                    else:
                        set_hy2_on()
                except Exception:
                    pass
            raise
        os.chmod(USERS_FILE, 0o640)
        try:
            shutil.chown(USERS_FILE, user="hy2-aio", group="hy2-aio")
        except Exception:
            pass
        snapshot = mutation_snapshot(users)
        if apply_hysteria:
            snapshot["apply_pending"] = True
    return snapshot


def apply_user_change(username: str, update, apply_hysteria: bool = True) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username not in users:
            raise ValueError("用户不存在")
        update(users[username])

    return mutate_users(mutator, apply_hysteria=apply_hysteria)


def add_user(username: str) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username in users:
            return
        users[username] = {
            "password": secrets.token_hex(16),
            "token": secrets.token_hex(24),
            "vless_id": new_vless_id(),
            "note": "",
            "disabled": False,
        }

    return mutate_users(mutator)


def remove_user(username: str) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username not in users:
            return
        if len(users) <= 1:
            raise ValueError("不能删除最后一个用户")
        del users[username]

    data = mutate_users(mutator)
    forget_user_side_state(username)
    return data


def rotate_user(username: str) -> dict[str, Any]:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名格式错误")

    def mutator(users: dict[str, Any]) -> None:
        if username not in users:
            raise ValueError("用户不存在")
        users[username]["password"] = secrets.token_hex(16)
        users[username]["token"] = secrets.token_hex(24)
        users[username]["vless_id"] = new_vless_id()

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
    return direct_links(env, username, password, info)


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
        if len(RATE_BUCKETS) > 256:
            stale = [
                old_key
                for old_key, stamps in RATE_BUCKETS.items()
                if not stamps or stamps[-1] < cutoff
            ]
            for old_key in stale:
                RATE_BUCKETS.pop(old_key, None)
        return True


LOG_EXPORT_UNITS = (
    "hysteria-server.service",
    "hy2-xray.service",
    "hy2-aio.service",
    "caddy.service",
)
LOG_EXPORT_MAX_LINES = 10000
LOG_EXPORT_RANGES = {
    "1h": "1 hour ago",
    "24h": "24 hours ago",
    "3d": "3 days ago",
}


def journalctl_export_args(range_key: str = "24h") -> list[str]:
    key = str(range_key or "24h").strip() or "24h"
    since = LOG_EXPORT_RANGES.get(key)
    if since is None:
        raise ValueError("导出范围无效")
    args = ["journalctl"]
    for unit in LOG_EXPORT_UNITS:
        args.extend(["-u", unit])
    args.extend(["--no-pager", "--since", since, "-n", str(LOG_EXPORT_MAX_LINES)])
    return args


def export_service_logs(range_key: str = "24h") -> tuple[bytes, str]:
    args = journalctl_export_args(range_key)
    try:
        result = subprocess.run(args, capture_output=True, timeout=15, check=False)
    except FileNotFoundError as error:
        raise RuntimeError("本机没有 journalctl") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("导出日志超时") from error
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "导出日志失败")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    body = result.stdout or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return body, f"hy2-logs-{stamp}.txt"


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
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def send_text_download(self, body: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
            body = subscription_yaml(env, username, str(info["password"]), info)
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
            self.send_subscription(path[3:].strip("/"))
            return
        # 兼容旧分拆版：GET /{token}（无 /s/ 前缀）
        bare = path.strip("/")
        if bare and "/" not in bare and all(c in "0123456789abcdefABCDEF" for c in bare) and 32 <= len(bare) <= 64:
            self.send_subscription(bare)
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
                data = apply_user_change(
                    username,
                    lambda info: info.update({"note": note}),
                    apply_hysteria=False,
                )
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
        except PermissionError as error:
            self.send_json(500, {"ok": False, "error": str(error)})
            print(f"[hy2-aio] permission error: {error}", flush=True)
            return
        except RuntimeError as error:
            self.send_json(500, {"ok": False, "error": str(error)})
            print(f"[hy2-aio] runtime error: {error}", flush=True)
            return
        apply_pending = bool(data.pop("apply_pending", False))
        response: dict[str, Any] = {
            "ok": True,
            "generated_at": data["generated_at"],
            "hy2_enabled": bool(data.get("server", {}).get("hy2_enabled", True)),
        }
        if action in ("disable", "remove") and not response["hy2_enabled"]:
            response["message"] = "已无启用用户，HY2 已关闭"
        self.send_json(200, response)
        if apply_pending:
            schedule_apply_and_collect()

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
            if path == "/hy2/off":
                data = hy2_turn_off()
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "hy2_enabled": False,
                        "generated_at": data["generated_at"],
                    },
                )
                return
            if path == "/hy2/on":
                try:
                    data = hy2_turn_on()
                except ValueError as error:
                    self.send_json(400, {"ok": False, "error": str(error)})
                    return
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "hy2_enabled": True,
                        "generated_at": data["generated_at"],
                    },
                )
                return
            if path == "/sync":
                data = collect()
                self.send_json(200, {"ok": True, "generated_at": data["generated_at"]})
                return
            if path == "/logs/export":
                payload = self.read_body()
                range_key = str(payload.get("range", "24h") or "24h").strip() or "24h"
                try:
                    body, filename = export_service_logs(range_key)
                except ValueError as error:
                    self.send_json(400, {"ok": False, "error": str(error)})
                    return
                except RuntimeError as error:
                    self.send_json(500, {"ok": False, "error": str(error)})
                    return
                self.send_text_download(body, filename)
                return
            if path == "/backup":
                data = collect(run_backup=False)
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
            if path == "/user/traffic":
                payload = self.read_body()
                try:
                    data = user_traffic_analysis(str(payload.get("username", "")).strip())
                except ValueError as error:
                    self.send_json(400, {"ok": False, "error": str(error)})
                    return
                self.send_json(200, {"ok": True, **data})
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
        except PermissionError as error:
            self.send_json(500, {"ok": False, "error": str(error)})
            print(f"[hy2-aio] api permission error: {error}", flush=True)
            return
        except RuntimeError as error:
            self.send_json(500, {"ok": False, "error": str(error)})
            print(f"[hy2-aio] api runtime error: {error}", flush=True)
            return
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as error:
            try:
                self.send_json(500, {"ok": False, "error": "内部错误"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
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
        check_runtime_permissions()
    except Exception as error:
        print(f"[hy2-aio] permission check failed: {error}", flush=True)
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
