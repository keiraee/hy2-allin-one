#!/usr/bin/env python3
from __future__ import annotations

import base64
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
import sys
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

for _cand in (
    str(Path(__file__).resolve().parent) if "__file__" in globals() else "",
    "/usr/local/lib/hy2-aio",
    str(Path.cwd() / "app"),
):
    if _cand and _cand not in sys.path and (Path(_cand) / "common.py").is_file():
        sys.path.insert(0, _cand)

from common import (
    atomic_bytes,
    atomic_json,
    client_insecure,
    counter_delta,
    country_code_to_flag,
    obfs_enabled,
    port_hop_enabled,
    port_hop_interval,
    port_hop_ports,
    public_base_url,
    read_env_file,
    reality_dest,
    reality_server_name,
    subscription_sni,
    user_is_disabled,
    xray_port,
)

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
    "usr/local/lib/hy2-aio/activity.py",
    "usr/local/lib/hy2-aio/common.py",
    "usr/local/lib/hy2-aio/subscription.py",
    "usr/local/lib/hy2-aio/hysteria-control.sh",
    "usr/local/lib/hy2-aio/xray-control.sh",
    "usr/local/lib/hy2-aio/xray-prestart.sh",
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
PORT_RESULT_FILE = Path("/run/hy2-aio/port-result")
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
    return read_env_file(ENV_FILE)


def load_users() -> dict[str, dict[str, str]]:
    data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("users.json 格式错误")
    return data


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



def hysteria_instance_marker() -> str:
    """Hysteria 进程的启动标识，用来判断它是否重启过。

    读 /proc/<pid>/stat 的第 22 列（starttime，开机以来的 jiffies）。
    配合 PID 一起用：只有 PID 和 starttime 都一样才算同一个进程
    （PID 会被复用，单看 PID 不可靠）。取不到就返回空串，调用方退化处理。
    """
    try:
        pid = subprocess.run(
            ["systemctl", "show", "hysteria-server.service", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=3, check=False,
        ).stdout.strip()
        if not pid.isdigit() or int(pid) <= 0:
            return ""
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # comm 字段可能含空格，从最后一个 ')' 之后开始切
        fields = stat[stat.rindex(")") + 2 :].split()
        starttime = fields[19]  # 相对 split 后的索引，对应第 22 列
        return f"{pid}@{starttime}"
    except Exception:
        return ""


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


def hysteria_api(
    path: str,
    secret: str,
    *,
    attempts: int = 10,
    delay: float = 0.3,
    method: str = "GET",
    body: Any = None,
) -> Any:
    """调用 Hysteria 流量统计 API。

    Hysteria 用 Authorization 头做鉴权（不是 Bearer）。POST /kick 是唯一的
    写接口，body 直接是一个用户名字符串的 JSON 数组。
    """
    stats_port = load_env().get("STATS_PORT", "9999")
    url = f"http://127.0.0.1:{stats_port}" + path
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    last_error: Optional[BaseException] = None
    for attempt in range(max(attempts, 1)):
        headers = {"Authorization": secret, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = response.read()
                if not payload.strip():
                    return {}
                return json.loads(payload)
        except Exception as error:
            last_error = error
            if attempt + 1 >= attempts or not is_transient_hysteria_error(error):
                raise
            time.sleep(delay)
    raise last_error or RuntimeError(f"Hysteria API 失败：{path}")


def kick_user_safely(username: str) -> int:
    """尽力踢掉一个用户，返回实际踢掉的人数（0 表示没踢）。

    这是「加分项」而不是主流程：Hysteria 没在跑、API secret 不对、
    或者功能已关闭，都不该让禁用/删除操作失败。所以这里吞掉所有异常，
    只打日志。
    """
    try:
        if hy2_is_off():
            return 0
        env = load_env()
        secret = str(env.get("API_SECRET") or "").strip()
        if not secret:
            return 0
        return kick_users([username], secret)
    except Exception as error:
        print(f"[hy2-aio] kick {username} failed: {error}", flush=True)
        return 0


def kick_users(usernames: list[str], secret: str) -> int:
    """把用户踢下线，返回实际提交的人数。

    注意 Hysteria 官方文档的提醒：客户端自带重连逻辑，踢掉之后会立刻重连。
    所以「踢人」必须和「验证后端已屏蔽该用户」一起做 —— 我们的验证后端就是
    users.json 的 disabled 字段。调用方必须先落盘再踢，顺序不能反。
    """
    names = [str(name).strip() for name in usernames if str(name).strip()]
    if not names:
        return 0
    hysteria_api("/kick", secret, method="POST", body=names, attempts=3, delay=0.2)
    return len(names)


def service_status(name: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", name],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def read_cpu_counters() -> tuple[int, int]:
    """返回 (累计 jiffies, 累计 idle jiffies)。

    idle 取 idle 列 + iowait 列：iowait 期间 CPU 并没有真在算，
    算进 idle 才是「忙不忙」的正确口径（与 top 一致）。
    """
    parts = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    values = [int(item) for item in parts]
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return total, idle


# 上一次采样点。用模块级变量而不是每次 sleep，是为了让「两次采样间隔」
# 至少等于采集周期（60s），而不是一个 120ms 的窄窗口——
# 100Hz 内核上 120ms 只有 12 jiffies/核，1% 的负载折算下来才 0.12 jiffies，
# 四舍五入永远是 0.0%，小机器上常驻进程的 1~2% 完全测不出来。
_cpu_samples: dict[str, Any] = {}
_CPU_MIN_WINDOW = 1.0  # 增量窗口短于这个值时，沿用上次读数而不是硬报一个数


def cpu_percent(window_seconds: float = 0.0) -> float:
    """CPU 使用率（%）。

    Args:
        window_seconds: >0 时在函数内阻塞采样这么长的窗口（用于一次性调用），
            0 表示用「距上次调用的增量」计算（用于周期采集）。
    """
    total, idle = read_cpu_counters()
    now = time.monotonic()
    previous = _cpu_samples.get("last")
    if window_seconds > 0:
        time.sleep(window_seconds)
        total2, idle2 = read_cpu_counters()
        delta_total = total2 - total
        delta_idle = idle2 - idle
        _cpu_samples["last"] = (total2, idle2, time.monotonic())
    elif previous is None:
        # 进程刚起来，还没有可比的基线。立刻补一次短窗口，总比返回 0 好。
        return cpu_percent(window_seconds=0.3)
    else:
        # 用户每点一次按钮都会触发一次 collect，间隔可能只有一两秒。
        # 窗口太窄时分母（jiffies 增量）小得离谱，算出来全是 0 或 100。
        # 这种情况沿用上次读数，而不是硬编一个假数字。
        if now - previous[2] < _CPU_MIN_WINDOW:
            return float(_cpu_samples.get("last_percent", 0.0))
        delta_total = total - previous[0]
        delta_idle = idle - previous[1]
        _cpu_samples["last"] = (total, idle, now)

    # 增量太小说明两次采样挤在同一个 jiffy 里，这时给不出有意义的百分比。
    # 返回 0 会让人误以为「CPU 空闲」，所以宁可保留上一次的读数。
    if delta_total <= 0:
        return float(_cpu_samples.get("last_percent", 0.0))
    percent = (1 - delta_idle / delta_total) * 100
    percent = max(0.0, min(100.0, round(percent, 1)))
    _cpu_samples["last_percent"] = percent
    return percent


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


from subscription import (
    GEO_FAILURE_RETRY,
    VLESS_NODE_NAME,
    _GEO_CACHE,
    _http_get_json,
    direct_link,
    direct_links,
    flag_prefix,
    new_vless_id,
    normalize_subscription_format,
    server_country_code,
    subscription_base64,
    subscription_body as _subscription_body,
    subscription_format_from_ua,
    subscription_singbox as _subscription_singbox,
    subscription_yaml as _subscription_yaml,
    vless_link,
)


def subscription_singbox(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
) -> bytes:
    return _subscription_singbox(env, username, password, info, mode=mode_for_user(username))


def subscription_yaml(
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
) -> bytes:
    return _subscription_yaml(env, username, password, info, mode=mode_for_user(username))


def subscription_body(
    fmt: str,
    env: dict[str, str],
    username: str,
    password: str,
    info: Optional[dict[str, Any]] = None,
) -> tuple[bytes, str]:
    return _subscription_body(fmt, env, username, password, info, mode=mode_for_user(username))


def blank_state(iface: str) -> dict[str, Any]:
    rx, tx = net_counters(iface)
    return {
        "month": current_month(),
        "network": {"rx": rx, "tx": tx, "last_rx": rx, "last_tx": tx},
        "users": {},
        "last_history": 0,
    }


def backup_corrupt_state() -> str:
    backup = STATE_FILE.with_name("state.json.corrupt")
    try:
        shutil.copy2(STATE_FILE, backup)
        return str(backup)
    except Exception as error:
        print(f"[hy2-aio] corrupt state backup failed: {error}", flush=True)
        return ""


def load_state(iface: str) -> tuple[dict[str, Any], str]:
    """读取统计状态；损坏时保留副本并返回错误文案，不静默清零。"""
    if not STATE_FILE.exists():
        return blank_state(iface), ""
    reason = ""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            reason = "state.json 结构异常（不是对象）"
    except Exception as error:
        data = None
        reason = f"state.json 无法解析（{error}）"
    if not reason:
        return data, ""
    backup = backup_corrupt_state()
    suffix = f"，已保留副本 {backup}" if backup else "，且副本备份失败"
    return blank_state(iface), f"{reason}；流量统计从零开始{suffix}"


def drop_stale_user_state(state: dict[str, Any], users: dict[str, Any]) -> None:
    """回收不在 users.json 里的用户残留。

    删用户清理与周期采集是跨进程读改写，残留可能被并发写"复活"；
    采集统一回收后，竞态最长存活一个采集周期，无需跨进程锁。
    """
    users_state = state.get("users")
    if isinstance(users_state, dict):
        for name in [key for key in users_state if key not in users]:
            users_state.pop(name, None)
    destinations = state.get("destinations")
    if isinstance(destinations, dict):
        for name in [key for key in destinations if key not in users]:
            destinations.pop(name, None)
    client_ips = state.get("client_ips")
    if isinstance(client_ips, dict):
        for name in [key for key in client_ips if key not in users]:
            client_ips.pop(name, None)
    stream_bytes = state.get("stream_bytes")
    if isinstance(stream_bytes, dict):
        for key in [key for key in stream_bytes if str(key).split(":", 1)[0] not in users]:
            stream_bytes.pop(key, None)


def collect(run_backup: bool = True) -> dict[str, Any]:
    global LAST_BACKUP_ERROR, BACKUP_RETRY_AFTER
    with LOCK:
        env = load_env()
        users = load_users()
        modes = load_modes()
        iface = env["NETWORK_INTERFACE"]
        total_limit = int(env["TOTAL_BYTES"])
        state, state_error = load_state(iface)

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

        errors: list[str] = [state_error] if state_error else []
        hy2_enabled = not hy2_is_off()
        traffic: dict[str, Any] = {}
        online: dict[str, Any] = {}
        stream_dump: list[Any] = []

        # Hysteria 重启后，它自己的 per-user 计数器从 0 重来。如果还拿新值跟
        # 旧值比差额，要么少算（新值 > 旧值 → 只记差额）、要么把重启后的全部
        # 当新增。这里用「PID@starttime」识别进程是否换过，换过就把所有用户
        # 的 last_tx/last_rx 基线清零，下次采集从 0 起算，不会再算错。
        instance = hysteria_instance_marker() if hy2_enabled else ""
        if instance and state.get("hysteria_instance") not in (None, "", instance):
            for user_state in state.get("users", {}).values():
                if isinstance(user_state, dict):
                    user_state["last_tx"] = 0
                    user_state["last_rx"] = 0
            # stream 缓存按「用户:connection:stream」做键，重启后全失效
            state["stream_bytes"] = {}
        if instance:
            state["hysteria_instance"] = instance

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
            raw = mapping_get_ci(traffic, username, users)
            raw = raw if isinstance(raw, dict) else None
            if raw is not None:
                tx, rx = accumulate_user_traffic(user_state, raw)
            else:
                tx = rx = 0
            devices_raw = mapping_get_ci(online, username, users)
            try:
                devices = int(devices_raw or 0)
            except (TypeError, ValueError):
                devices = 0
            if tx or rx or devices:
                user_state["last_active"] = timestamp

            client_mode = mode_for_user(username, modes)
            recent_ips = client_ips_for_user(state, username)
            output_users.append(
                {
                    "username": username,
                    "note": str(info.get("note", "")),
                    "disabled": user_is_disabled(info),
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

        drop_stale_user_state(state, users)

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
                "cpu_cores": os.cpu_count() or 1,
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
                # 端口：面板「端口设置」弹窗要显示当前值。
                # HY2 范围（端口跳跃）优先展示完整范围。
                "ports": {
                    "hy2": str(port_hop_ports(env) or env.get("HY2_PORT", "443") or ""),
                    "vless": str(xray_port(env) or ""),
                },
                # 归属地只在这里解析一次，落盘给访问资料文件复用（见 lib/access.sh）：
                # 节点名的国旗必须处处一致，CLI 那边不能自己再发一遍网络请求。
                "country_code": server_country_code(env),
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


def request_port_change(target: str, value: str) -> bool:
    """让 root 侧执行 hy2 port（面板无权写 config.env，走 cmd 文件机制）。

    复用 hysteria 的 cmd 文件 + path unit：内容写 port:<target>:<value>，
    hysteria-control.sh 认出 port: 前缀后以 root 跑 `hy2 port`。
    返回是否在超时内完成（flag 消失 = root 侧处理完了）。
    """
    if target not in ("hy2", "vless"):
        raise ValueError(f"未知端口目标：{target}")
    value = str(value or "").strip()
    if not value:
        raise ValueError("端口值不能为空")
    # 只放行安全字符：数字、短横线（范围）
    import re as _re
    if not _re.fullmatch(r"[0-9]+(?:-[0-9]+)?", value):
        raise ValueError("端口格式无效")
    _unlink_quiet(HYSTERIA_RELOAD_FLAG)
    _unlink_quiet(PORT_RESULT_FILE)
    HYSTERIA_CMD_FILE.write_text(f"port:{target}:{value}" + chr(10), encoding="utf-8")
    HYSTERIA_RELOAD_FLAG.write_text(str(time.time()), encoding="utf-8")
    for _ in range(150):          # 最多 30 秒：改端口含重建+重启，比普通 restart 慢
        time.sleep(0.2)
        if not HYSTERIA_RELOAD_FLAG.exists():
            result_text = ""
            if PORT_RESULT_FILE.exists():
                try:
                    result_text = PORT_RESULT_FILE.read_text(encoding="utf-8").strip()
                except OSError:
                    result_text = ""
                _unlink_quiet(PORT_RESULT_FILE)
            if result_text.startswith("ERR:"):
                raise ValueError(result_text[4:].strip() or "端口变更失败")
            return True
    return False


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
    request_hysteria("restart")
    return collect()


from activity import (
    CLIENT_ADDR_KEYS,
    CLIENT_IP_MAX,
    DEST_MAX_PER_USER,
    LOG_ISO_RE,
    TRAFFIC_HISTORY_DAYS,
    USERNAME_PATTERN,
    apply_seen_time,
    canonical_username as _canonical_username,
    client_ips_for_user as _client_ips_for_user,
    history_files as _history_files,
    hysteria_connect_log_lines,
    is_ip_host,
    is_plausible_host,
    live_streams_from_payload,
    load_user_history_rows as _load_user_history_rows,
    mapping_get_ci as _mapping_get_ci,
    nested_bucket_ci as _nested_bucket_ci,
    normalize_streams_payload,
    parse_history_time,
    parse_hysteria_connect_line,
    prune_client_ips,
    record_client_ip,
    remember_client_ips as _remember_client_ips,
    remember_log_destinations as _remember_log_destinations,
    remember_user_streams as _remember_user_streams,
    root_host,
    series_from_history,
    session_stats_from_logs as _session_stats_from_logs,
    sites_from_state,
    split_host_port,
    stamp_from_log_line,
    stream_client_addr,
    stream_target,
)


def registered_usernames() -> dict[str, Any]:
    try:
        users = load_users()
    except Exception:
        return {}
    return users if isinstance(users, dict) else {}


def canonical_username(name: str, users: Optional[dict[str, Any]] = None) -> str:
    roster = users if isinstance(users, dict) else registered_usernames()
    return _canonical_username(name, roster)


def mapping_get_ci(
    mapping: Any, username: str, users: Optional[dict[str, Any]] = None
) -> Any:
    roster = users if isinstance(users, dict) else registered_usernames()
    return _mapping_get_ci(mapping, username, roster)


def nested_bucket_ci(
    mapping: Any, username: str, users: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    roster = users if isinstance(users, dict) else registered_usernames()
    return _nested_bucket_ci(mapping, username, roster)


def session_stats_from_logs(log_lines: list[str], username: str) -> dict[str, Any]:
    return _session_stats_from_logs(log_lines, username, registered_usernames())


def remember_log_destinations(
    state: dict[str, Any], log_lines: list[str], timestamp: str
) -> None:
    _remember_log_destinations(state, log_lines, timestamp, registered_usernames())


def remember_client_ips(
    state: dict[str, Any],
    streams: list[Any],
    log_lines: list[str],
    timestamp: str,
) -> None:
    _remember_client_ips(state, streams, log_lines, timestamp, registered_usernames())


def client_ips_for_user(state: Any, username: str) -> list[dict[str, str]]:
    return _client_ips_for_user(state, username, registered_usernames())


def remember_user_streams(
    state: dict[str, Any], streams: list[Any], timestamp: str
) -> None:
    _remember_user_streams(state, streams, timestamp, registered_usernames())


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
    return live_streams_from_payload(payload, username, registered_usernames())


def sites_for_user(username: str) -> list[dict[str, Any]]:
    return sites_from_state(read_json(STATE_FILE, {}), username, registered_usernames())


def history_files() -> list[Path]:
    return _history_files(HISTORY_CSV)


def load_user_history_rows(username: str) -> list[tuple[datetime, int, int]]:
    return _load_user_history_rows(HISTORY_CSV, username)


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
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("state.json 结构异常")
        except Exception:
            # 损坏文件先留副本再覆盖，别让删用户顺手把现场毁了。
            backup_corrupt_state()
            state = {}
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
                "disabled": user_is_disabled(info),
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


def _apply_and_collect(kick_username: str = "") -> None:
    """按磁盘上的最新用户表重启内核，再采集。不回滚已提交的 users.json。"""
    with APPLY_LOCK:
        try:
            _apply_services()
        except Exception as error:
            set_apply_error(f"用户已保存，但内核未加载最新配置：{error}")
            print(f"[hy2-aio] post-mutation service apply gave up: {error}", flush=True)
        if kick_username:
            kick_user_safely(kick_username)
        _collect_after_mutation()


def schedule_apply_and_collect(kick_username: str = "") -> None:
    threading.Thread(
        target=_apply_and_collect,
        args=(kick_username,),
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
    # subscription 可带格式后缀：subscription / subscription-v2ray / subscription-singbox
    # 面板按客户端分类复制时用得上，省得用户自己往链接后面拼 ?fmt=
    if kind not in ("subscription", "subscription-v2ray", "subscription-singbox", "direct", "password"):
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
    if kind.startswith("subscription"):
        base = f"{public_base_url(env)}/s/{token}"
        fmt = {"subscription-v2ray": "v2ray", "subscription-singbox": "singbox"}.get(kind, "")
        return f"{base}?fmt={fmt}" if fmt else base
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
                url_port = parsed.port
            except Exception:
                return False
            host = (parsed.hostname or "").lower()
            if host != domain:
                return False
            if url_port is None:
                # 端口缺省时按协议补默认端口；面板不在默认端口时，
                # 隐含 443/80 的同域页面仍属跨端口，不能当同源。
                scheme = (parsed.scheme or "").lower()
                if scheme == "https":
                    url_port = 443
                elif scheme == "http":
                    url_port = 80
                else:
                    return False
            return str(url_port) == port

        # Origin: null（沙箱 iframe / data: / file://）视为跨站拒绝，
        # 否则配合浏览器缓存的 Basic Auth 可伪造 POST 改用户。
        if origin and not host_ok(origin):
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
        if user_is_disabled(info):
            self.send_json(403, {"ok": False, "error": "账号已被禁用"})
            return
        try:
            env = load_env()
            # 格式优先级：?fmt= 显式指定 > User-Agent 自动识别。
            # 显式参数永远优先 —— 有些客户端会伪造/缺省 UA，靠猜不可靠。
            # 用 getattr 兜底：单测用 stub handler 时可能没有 path 属性，
            # 真实运行时 do_GET/do_HEAD 一定有。缺了就当成没传 fmt。
            raw_path = getattr(self, "path", "") or ""
            query = urllib.parse.parse_qs(raw_path.split("?", 1)[1] if "?" in raw_path else "")
            forced = normalize_subscription_format((query.get("fmt") or [""])[0])
            fmt = forced or subscription_format_from_ua(self.headers.get("User-Agent", ""))
            body, content_type = subscription_body(fmt, env, username, str(info["password"]), info)
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
        self.send_header("Content-Type", content_type)
        # 文件名不给扩展名：部分客户端会拿扩展名反推格式，跟 Content-Type
        # 打架反而导不进去。格式区分交给 Content-Type 和 ?fmt= 参数。
        self.send_header("Content-Disposition", f"attachment; filename=HY2-{username}")
        # 整机取网卡计数（rx/tx 为网卡收发），上下行无法真实拆分，仅和值有意义；
        # 命名沿用全站约定 upload≙tx。Hysteria 口径经上游 core/server 核对：
        # tx=客户端上行、rx=客户端下行。
        self.send_header(
            "Subscription-Userinfo",
            f"upload={tx}; download={rx}; total={limit}; expire=0",
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

        # 禁用/删除/轮换密钥之后，这个人可能还挂着已经建立的 QUIC 连接。
        # Hysteria 的 userpass 在重载新 config.yaml 前仍持有旧密码表，
        # 因此当 apply_pending 为真时，把踢人延后到内核重启完成之后再执行，
        # 避免重启前踢人被客户端立即重连绕过。
        kick_target = ""
        if action in ("disable", "remove", "rotate"):
            if apply_pending:
                kick_target = username
            else:
                kicked = kick_user_safely(username)
                if kicked:
                    response["kicked"] = kicked

        self.send_json(200, response)
        if apply_pending:
            schedule_apply_and_collect(kick_target)

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
        # 只收 application/json：text/plain 简单请求可绕过 CORS 预检，
        # 是 CSRF 的载体；JSON 类型会触发预检，浏览器侧直接挡住。
        content_type = str(self.headers.get("Content-Type", "") or "")
        content_type = content_type.split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_json(415, {"ok": False, "error": "需要 Content-Type: application/json"})
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
            if path == "/ports":
                payload = self.read_body()
                target = str(payload.get("target", "")).strip().lower()
                value = str(payload.get("value", "")).strip()
                try:
                    ok_done = request_port_change(target, value)
                except ValueError as error:
                    self.send_json(400, {"ok": False, "error": str(error)})
                    return
                if not ok_done:
                    self.send_json(500, {"ok": False, "error": "端口变更超时（root 侧未响应）"})
                    return
                # 后端被 port 流程重启过，读一下最新状态回给前端
                data = collect()
                self.send_json(
                    200,
                    {"ok": True, "target": target, "value": value, "generated_at": data["generated_at"]},
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
            if path == "/user/kick":
                # 只断开现有连接，不动 users.json —— 跟他重连还会成功。
                # 跟「禁用」的区别就在这里：禁用是先屏蔽再踢（回不来），
                # 这个是纯踢（想让他换个 IP 重连就用这个）。
                payload = self.read_body()
                username = str(payload.get("username", "")).strip()
                if not USERNAME_PATTERN.fullmatch(username):
                    self.send_json(400, {"ok": False, "error": "用户名格式错误"})
                    return
                if username not in load_users():
                    self.send_json(400, {"ok": False, "error": "用户不存在"})
                    return
                kicked = kick_user_safely(username)
                if kicked:
                    self.send_json(200, {"ok": True, "kicked": kicked})
                else:
                    self.send_json(
                        200, {"ok": True, "kicked": 0, "message": "没有可断开的连接（或 Hysteria 未运行）"}
                    )
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
