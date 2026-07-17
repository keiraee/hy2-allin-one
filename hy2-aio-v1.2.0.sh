#!/usr/bin/env bash
# HY2 AIO - Hysteria 2 + multi-user subscriptions + lightweight dashboard
# Supported: Debian 11+/Ubuntu 22.04+, systemd, amd64/arm64
set -Eeuo pipefail
umask 077

SCRIPT_VERSION="1.2.0"
AIO_VERSION="$SCRIPT_VERSION"
CONFIG_DIR="/etc/hy2-aio"
ENV_FILE="${CONFIG_DIR}/config.env"
USERS_FILE="${CONFIG_DIR}/users.json"
MODE_FILE="${CONFIG_DIR}/client-mode.json"
HYSTERIA_CONFIG="/etc/hysteria/config.yaml"
HYSTERIA_CERT="/etc/hysteria/server.crt"
HYSTERIA_KEY="/etc/hysteria/server.key"
APP_DIR="/usr/local/lib/hy2-aio"
APP_FILE="${APP_DIR}/server.py"
REBUILD_FILE="${APP_DIR}/rebuild_config.py"
WEB_DIR="/var/www/hy2-aio"
STATE_DIR="/var/lib/hy2-aio"
ACCESS_FILE="/root/hy2-aio-access.txt"
CADDY_FILE="/etc/caddy/Caddyfile"
SERVICE_FILE="/etc/systemd/system/hy2-aio.service"
SELF_INSTALL="/usr/local/sbin/hy2ctl"

log() { printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

need_root() {
  [ "$(id -u)" -eq 0 ] || die "请使用 root 运行：sudo bash $0 ${1:-install}"
}

have_systemd() {
  command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

PKG_MANAGER=""

detect_platform() {
  have_systemd || die "This release requires systemd"
  [ -r /etc/os-release ] || die "Cannot detect Linux distribution"
  # shellcheck disable=SC1091
  . /etc/os-release
  if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
  elif command -v yum >/dev/null 2>&1; then
    PKG_MANAGER="yum"
  elif command -v zypper >/dev/null 2>&1; then
    PKG_MANAGER="zypper"
  else
    die "Unsupported package manager on ${PRETTY_NAME:-unknown}"
  fi
  log "Detected ${PRETTY_NAME:-unknown}; package manager: $PKG_MANAGER"
}

rand_hex() { openssl rand -hex "${1:-16}"; }
valid_name() { [[ "${1:-}" =~ ^[A-Za-z0-9_-]{1,32}$ ]]; }

read_env() {
  [ -f "$ENV_FILE" ] || die "尚未安装。请运行：sudo bash $0 install"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  HY2_PORT="${HY2_PORT:-443}"
  PANEL_PORT="${PANEL_PORT:-443}"
  STATS_PORT="${STATS_PORT:-9999}"
}

ensure_mode_file() {
  install -d -o root -g hysteria -m 0750 "$CONFIG_DIR"
  python3 - "$MODE_FILE" "$USERS_FILE" <<'PY'
import json
import os
import sys
from pathlib import Path

mode_path = Path(sys.argv[1])
users_path = Path(sys.argv[2])

try:
    users = json.loads(users_path.read_text(encoding="utf-8"))
except Exception:
    users = {}

try:
    raw = json.loads(mode_path.read_text(encoding="utf-8"))
except Exception:
    raw = {}

def normalize(value):
    if not isinstance(value, dict):
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    mode = str(value.get("mode", "bbr")).lower()
    if mode != "brutal":
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    if up <= 0 or down <= 0:
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    return {"mode": "brutal", "up_mbps": up, "down_mbps": down}

# 兼容早期全局扁平格式：{"mode":"brutal", ...}
if isinstance(raw, dict) and "mode" in raw:
    data = {"default": normalize(raw), "users": {}}
else:
    default = normalize(raw.get("default", {}) if isinstance(raw, dict) else {})
    overrides = raw.get("users", {}) if isinstance(raw, dict) else {}
    clean = {}
    if isinstance(overrides, dict):
        for username, value in overrides.items():
            if username in users:
                clean[username] = normalize(value)
    data = {"default": default, "users": clean}

temporary = mode_path.with_suffix(mode_path.suffix + ".tmp")
temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temporary, mode_path)
PY
  chown root:hysteria "$MODE_FILE"
  chmod 0640 "$MODE_FILE"
}

api_post() {
  curl -fsS --connect-timeout 5 --max-time 60 \
    -X POST "http://127.0.0.1:18081/$1"
}

detect_public_ipv4() {
  local ip="" endpoint
  for endpoint in \
    "https://api.ipify.org" \
    "https://ipv4.icanhazip.com" \
    "https://ifconfig.me/ip"; do
    ip="$(curl -4fsS --connect-timeout 5 --max-time 10 "$endpoint" 2>/dev/null | tr -d '[:space:]' || true)"
    if python3 - "$ip" <<'PY' >/dev/null 2>&1
import ipaddress, sys
try:
    value = ipaddress.ip_address(sys.argv[1])
    assert value.version == 4 and not value.is_private
except Exception:
    raise SystemExit(1)
PY
    then
      printf '%s' "$ip"
      return 0
    fi
  done
  return 1
}

detect_iface() {
  ip -4 route show default 2>/dev/null | awk 'NR==1 {print $5}'
}

prompt_value() {
  local prompt="$1" default="$2" value=""
  if [ -t 0 ] && [ "${HY2_NONINTERACTIVE:-0}" != "1" ]; then
    read -r -p "${prompt} [${default}]: " value || true
  fi
  printf '%s' "${value:-$default}"
}

port_is_used() {
  local port="$1"
  ss -Hlunp 2>/dev/null | awk -v p=":$port" '$5 ~ p"$" || $5 ~ p" " {found=1} END {exit !found}'
}

tcp_port_is_used() {
  local port="$1"
  ss -Hlntp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" || $4 ~ p" " {found=1} END {exit !found}'
}

prompt_panel_port() {
  local value="${HY2_PANEL_PORT:-}" default="443"
  while true; do
    value="${value:-$(prompt_value 'Panel HTTPS TCP port' "$default")}" 
    [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || {
      warn "Port must be an integer from 1 to 65535"
      value=""
      continue
    }
    if tcp_port_is_used "$value"; then
      warn "TCP port $value is already in use"
      value=""
      continue
    fi
    printf '%s' "$value"
    return
  done
}

prompt_stats_port() {
  local value="${HY2_STATS_PORT:-}" default="9999"
  while true; do
    value="${value:-$(prompt_value 'Internal stats TCP port' "$default")}" 
    [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || {
      warn "Port must be an integer from 1 to 65535"
      value=""
      continue
    }
    if tcp_port_is_used "$value"; then
      warn "TCP port $value is already in use"
      value=""
      continue
    fi
    printf '%s' "$value"
    return
  done
}

prompt_hysteria_port() {
  local value="${HY2_PORT:-}" default="443"
  while true; do
    value="${value:-$(prompt_value 'Hysteria UDP port' "$default")}" 
    [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || {
      warn "Port must be an integer from 1 to 65535"
      value=""
      continue
    }
    if port_is_used "$value"; then
      warn "UDP port $value is already in use"
      value=""
      continue
    fi
    printf '%s' "$value"
    return
  done
}

install_packages() {
  log "安装基础依赖"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    curl ca-certificates openssl python3 jq tar gzip \
    iproute2 procps util-linux gpg debian-keyring \
    debian-archive-keyring apt-transport-https
}

install_packages_v12() {
  log "Installing base dependencies"
  case "$PKG_MANAGER" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y curl ca-certificates openssl python3 jq tar gzip \
        iproute2 procps util-linux gpg debian-keyring debian-archive-keyring \
        apt-transport-https
      ;;
    dnf|yum)
      "$PKG_MANAGER" install -y curl ca-certificates openssl python3 jq tar gzip \
        iproute procps-ng util-linux gnupg2
      ;;
    zypper)
      zypper --non-interactive install curl ca-certificates openssl python3 jq tar gzip \
        iproute2 procps util-linux gpg2
      ;;
    *) die "No dependency adapter for $PKG_MANAGER" ;;
  esac
}

install_caddy() {
  if command -v caddy >/dev/null 2>&1; then
    log "Caddy 已存在：$(caddy version 2>/dev/null || true)"
    return
  fi

  log "安装 Caddy"
  install -d -m 0755 /usr/share/keyrings /etc/apt/sources.list.d
  if curl -1fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor --batch --yes \
      -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1fsSL 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      -o /etc/apt/sources.list.d/caddy-stable.list; then
    chmod o+r \
      /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
      /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get install -y caddy
  else
    warn "Caddy 官方仓库添加失败，尝试系统仓库"
    apt-get install -y caddy
  fi
  command -v caddy >/dev/null 2>&1 || die "Caddy 安装失败"
}

install_caddy_v12() {
  command -v caddy >/dev/null 2>&1 && return
  if [ "$PKG_MANAGER" = "apt" ]; then
    install_caddy
    return
  fi
  "$PKG_MANAGER" install -y caddy >/dev/null 2>&1 || true
  if ! command -v caddy >/dev/null 2>&1; then
    local arch
    case "$(uname -m)" in
      x86_64) arch=amd64 ;;
      aarch64|arm64) arch=arm64 ;;
      *) die "Unsupported CPU architecture for Caddy: $(uname -m)" ;;
    esac
    curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=$arch" -o /tmp/caddy
    install -m 0755 /tmp/caddy /usr/local/bin/caddy
    rm -f /tmp/caddy
  fi
  getent group caddy >/dev/null 2>&1 || groupadd --system caddy
  id caddy >/dev/null 2>&1 || useradd --system --gid caddy --home /var/lib/caddy --shell /usr/sbin/nologin caddy
  install -d -o caddy -g caddy -m 0750 /var/lib/caddy /var/log/caddy
  cat > /etc/systemd/system/caddy.service <<'EOF'
[Unit]
Description=Caddy
After=network-online.target
Wants=network-online.target
[Service]
User=caddy
Group=caddy
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable caddy.service >/dev/null
  command -v caddy >/dev/null 2>&1 || die "Caddy installation failed"
}

configure_firewall_v12() {
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    ufw allow "$PANEL_PORT/tcp" >/dev/null
    ufw allow "$HY2_PORT/udp" >/dev/null
    return
  fi
  if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="$PANEL_PORT/tcp" >/dev/null
    firewall-cmd --permanent --add-port="$HY2_PORT/udp" >/dev/null
    firewall-cmd --reload >/dev/null
    return
  fi
  warn "Firewall was not changed; allow TCP $PANEL_PORT and UDP $HY2_PORT manually if needed"
}

install_hysteria() {
  if command -v hysteria >/dev/null 2>&1; then
    log "Hysteria 已存在：$(hysteria version 2>/dev/null | head -1 || true)"
    return
  fi
  log "通过官方脚本安装 Hysteria 2"
  bash <(curl -fsSL https://get.hy2.sh/)
  command -v hysteria >/dev/null 2>&1 || die "Hysteria 安装失败"
}

configure_swap_and_kernel() {
  log "配置 Swap、BBR 与 UDP 缓冲"
  local mem_kb
  mem_kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
  if [ "${mem_kb:-0}" -lt 1048576 ] && ! swapon --show --noheadings | grep -q .; then
    if [ ! -f /swapfile ]; then
      fallocate -l 1G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
    fi
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null 2>&1 || true
    swapon /swapfile || true
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi

  modprobe tcp_bbr 2>/dev/null || true
  echo tcp_bbr > /etc/modules-load.d/tcp_bbr.conf
  cat > /etc/sysctl.d/99-hy2-aio.conf <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.core.rmem_max=16777216
net.core.wmem_max=16777216
EOF
  /usr/sbin/sysctl --system >/dev/null 2>&1 || true
}

write_rebuild_helper() {
  install -d -m 0755 "$APP_DIR"
  cat > "$REBUILD_FILE" <<'PY'
#!/usr/bin/env python3
import json
import os
from pathlib import Path

ENV_FILE = Path("/etc/hy2-aio/config.env")
USERS_FILE = Path("/etc/hy2-aio/users.json")
MODE_FILE = Path("/etc/hy2-aio/client-mode.json")
OUT_FILE = Path("/etc/hysteria/config.yaml")

def read_env(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key] = value
    return values

env = read_env(ENV_FILE)
users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
if not users:
    raise SystemExit("users.json 不能为空")

lines = [
    f'listen: ":{env.get("HY2_PORT", "443")}"',
    "",
    "tls:",
    '  cert: "/etc/hysteria/server.crt"',
    '  key: "/etc/hysteria/server.key"',
    "  sniGuard: disable",
    "",
    "auth:",
    "  type: userpass",
    "  userpass:",
]
for username, info in sorted(users.items()):
    lines.append(f"    {json.dumps(username)}: {json.dumps(str(info['password']))}")

lines.extend([
    "",
    "obfs:",
    "  type: salamander",
    "  salamander:",
    f"    password: {json.dumps(env['OBFS_PASSWORD'])}",
    "",
    "congestion:",
    "  type: bbr",
    "  bbrProfile: standard",
    "",
    "speedTest: true",
    "disableUDP: false",
    "",
    "trafficStats:",
    f'  listen: "127.0.0.1:{env.get("STATS_PORT", "9999")}"',
    f"  secret: {json.dumps(env['API_SECRET'])}",
    "",
])

temporary = OUT_FILE.with_suffix(".tmp")
temporary.write_text("\n".join(lines), encoding="utf-8")
os.replace(temporary, OUT_FILE)
PY
  chmod 0755 "$REBUILD_FILE"
}

write_backend() {
  cat > "$APP_FILE" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
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
from typing import Any

ENV_FILE = Path("/etc/hy2-aio/config.env")
USERS_FILE = Path("/etc/hy2-aio/users.json")
MODE_FILE = Path("/etc/hy2-aio/client-mode.json")
STATE_DIR = Path("/var/lib/hy2-aio")
STATE_FILE = STATE_DIR / "state.json"
BACKUP_DIR = STATE_DIR / "backups"
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
        values[key] = value
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


def mode_for_user(username: str, modes: dict[str, Any] | None = None) -> dict[str, Any]:
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


def direct_link(env: dict[str, str], username: str, password: str) -> str:
    auth = urllib.parse.quote(f"{username}:{password}", safe="")
    query = urllib.parse.urlencode(
        {
            "insecure": "1",
            "obfs": "salamander",
            "obfs-password": env["OBFS_PASSWORD"],
            "sni": env.get("SNI", "www.amazon.sg"),
        }
    )
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
    skip-cert-verify: true
    udp: true
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

            password = str(info["password"])
            token = str(info["token"])
            client_mode = mode_for_user(username, modes)
            output_users.append(
                {
                    "username": username,
                    "password": password,
                    "online": devices,
                    "upload": user_state["month_tx"],
                    "download": user_state["month_rx"],
                    "total": user_state["month_tx"] + user_state["month_rx"],
                    "lifetime_total": user_state["lifetime_tx"] + user_state["lifetime_rx"],
                    "last_active": user_state["last_active"],
                    "mode": mode_label(client_mode),
                    "subscription": f"https://{env['DOMAIN']}:{env.get('PANEL_PORT', '443')}/s/{token}",
                    "direct": direct_link(env, username, password),
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
             "历史累计字节", "最后活动", "速率模式", "订阅地址", "HY2基础直链"]
        )
        for user in users:
            writer.writerow(
                [
                    user["username"], user["online"], user["upload"], user["download"],
                    user["total"], user["lifetime_total"], user["last_active"],
                    user["mode"], user["subscription"], user["direct"],
                ]
            )
    os.replace(temporary, USERS_CSV)


def write_history(state: dict[str, Any], data: dict[str, Any]) -> None:
    now = time.time()
    if now - float(state.get("last_history", 0)) < 300:
        return
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


def create_backup(force: bool = False) -> Path | None:
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

    if backup.exists():
        shutil.copy2(backup, DOWNLOAD_DIR / "hy2-aio-backup-latest.tar.gz")

    cutoff = time.time() - int(load_env().get("BACKUP_RETENTION_DAYS", "14")) * 86400
    for path in BACKUP_DIR.glob("hy2-aio-backup-*.tar.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
    return backup if backup.exists() else None


def apply_web_permissions() -> None:
    for path in [DATA_FILE, USERS_CSV, HISTORY_CSV, DOWNLOAD_DIR / "hy2-aio-backup-latest.tar.gz"]:
        if path.exists():
            os.chmod(path, 0o640)
            try:
                shutil.chown(path, user="root", group="caddy")
            except Exception:
                pass


def subscription_for_token(token: str):
    for username, info in load_users().items():
        if str(info.get("token")) == token:
            return username, info
    return None, None


class Handler(BaseHTTPRequestHandler):
    server_version = "HY2AIO/1.0"

    def log_message(self, format_string: str, *args: Any) -> None:
        return

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
        username, info = subscription_for_token(token)
        if username is None or info is None:
            self.send_error(404)
            return
        try:
            data = collect()
            env = load_env()
            body = subscription_yaml(env, username, str(info["password"]))
            traffic = data["server"]["traffic"]
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/yaml; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="HY2-{username}.yaml"')
        self.send_header(
            "Subscription-Userinfo",
            f"upload={traffic['rx']}; download={traffic['tx']}; "
            f"total={traffic['limit']}; expire=0",
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
            self.send_subscription(path.removeprefix("/s/").strip("/"))
            return
        self.send_error(404)

    def do_POST(self) -> None:
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
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})
            return
        self.send_error(404)


def collector_loop() -> None:
    while True:
        try:
            collect()
        except Exception:
            pass
        time.sleep(60)


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    collect()
    threading.Thread(target=collector_loop, daemon=True).start()
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()


if __name__ == "__main__":
    main()
PY
  chmod 0755 "$APP_FILE"
}

write_panel() {
  install -d -o root -g caddy -m 0750 "$WEB_DIR" "$WEB_DIR/downloads"
  cat > "$WEB_DIR/index.html" <<'HTML'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>HY2 AIO Dashboard</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#17191c;background:#f4f5f7}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:30px 16px 64px}
.top,.head{display:flex;justify-content:space-between;align-items:center;gap:14px}.top{align-items:flex-end}
h1{font-size:26px;margin:0}.muted,.label{color:#737780}.actions,.services{display:flex;gap:8px;flex-wrap:wrap}
.btn,.pill{border:1px solid #d9dce1;border-radius:11px;background:#fff;color:inherit;text-decoration:none;padding:9px 12px;cursor:pointer}
.btn.primary{background:#17191c;color:#fff;border-color:#17191c}.btn:disabled{opacity:.55;cursor:wait}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:20px}
.card{background:#fff;border:1px solid #e3e5e8;border-radius:17px;padding:17px;box-shadow:0 2px 12px #00000008}
.value{font-size:21px;font-weight:760;margin-top:5px}.bar{height:8px;background:#eceef1;border-radius:8px;overflow:hidden;margin-top:13px}
.bar i{display:block;height:100%;background:#17191c}.ok{color:#137547;border-color:#b9dec9}.bad{color:#b42318;border-color:#f0b8b2}
.users{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.name{font-weight:750;font-size:17px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}.stat{background:#f5f6f8;border-radius:11px;padding:10px}.stat b{display:block}
h2{font-size:17px;margin:27px 0 12px}.notice{margin-top:14px;padding:12px 14px;background:#fff8e8;border:1px solid #f0dfaf;border-radius:12px}
.error{display:none;margin-top:14px;padding:12px 14px;background:#fff0ef;color:#b42318;border-radius:12px}
.footer{margin-top:26px;color:#777b82;font-size:12px}
@media(max-width:850px){.grid{grid-template-columns:repeat(2,1fr)}.users{grid-template-columns:1fr}}
@media(max-width:540px){.grid{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.stats{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>HY2 AIO Dashboard</h1>
      <div id="time" class="muted">正在读取数据…</div>
    </div>
    <div class="actions">
      <button id="syncBtn" class="btn primary" onclick="syncNow()">立即同步</button>
      <a class="btn" href="users.csv">用户 CSV</a>
      <a class="btn" href="history.csv">历史记录</a>
      <a class="btn" href="downloads/hy2-aio-backup-latest.tar.gz">完整备份</a>
    </div>
  </div>

  <div id="error" class="error"></div>
  <div class="notice">面板流量来自服务器网卡本地计数，适合日常观察；云厂商控制台和账单仍是最终计费依据。速率模式只写入 Clash 订阅，HY2 基础直链不包含带宽参数。</div>

  <div class="grid">
    <div class="card">
      <div class="label">本月整机流量</div><div id="traffic" class="value">--</div>
      <div id="remain" class="muted">--</div><div class="bar"><i id="trafficBar" style="width:0"></i></div>
    </div>
    <div class="card"><div class="label">CPU / 负载</div><div id="cpu" class="value">--</div><div id="load" class="muted">--</div></div>
    <div class="card"><div class="label">内存 / Swap</div><div id="memory" class="value">--</div><div id="swap" class="muted">--</div></div>
    <div class="card"><div class="label">磁盘 / 运行时间</div><div id="disk" class="value">--</div><div id="uptime" class="muted">--</div></div>
  </div>

  <h2>服务状态</h2><div id="services" class="services"></div>
  <h2>用户状态</h2><div id="users" class="users"></div>
  <div class="footer">数据每 60 秒采集，网页每 30 秒自动刷新。订阅、直链和备份均含敏感凭据，请勿公开分享。</div>
</div>

<script>
const $=id=>document.getElementById(id);
const esc=value=>String(value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));
const bytes=value=>{let n=Number(value||0),i=0;const u=["B","KB","MB","GB","TB"];while(n>=1000&&i<u.length-1){n/=1000;i++}return n.toFixed(i<2?2:1)+" "+u[i]};
const duration=seconds=>{seconds=Math.max(0,Math.floor(Number(seconds)||0));return Math.floor(seconds/86400)+" 天 "+Math.floor(seconds%86400/3600)+" 小时"};
async function copyText(text,button){try{await navigator.clipboard.writeText(text)}catch(e){prompt("复制下面内容：",text)}const old=button.textContent;button.textContent="已复制";setTimeout(()=>button.textContent=old,1200)}
async function syncNow(){const btn=$("syncBtn"),old=btn.textContent;btn.disabled=true;btn.textContent="同步中…";try{const response=await fetch("api/sync",{method:"POST",cache:"no-store"});const result=await response.json().catch(()=>({}));if(!response.ok||!result.ok)throw new Error(result.error||("HTTP "+response.status));await load();btn.textContent="同步完成"}catch(error){btn.textContent="同步失败";alert("同步失败："+error.message)}setTimeout(()=>{btn.disabled=false;btn.textContent=old},1500)}
async function load(){
  try{
    const response=await fetch("data.json?t="+Date.now(),{cache:"no-store"});if(!response.ok)throw new Error("HTTP "+response.status);
    const data=await response.json(),t=data.server.traffic;
    $("time").textContent="更新时间："+data.generated_at+" · "+data.server.ip+" · "+data.server.domain;
    $("traffic").textContent=bytes(t.used)+" / "+bytes(t.limit);
    $("remain").textContent="接收 "+bytes(t.rx)+" · 发送 "+bytes(t.tx)+" · 剩余 "+bytes(t.remain)+" · "+Number(t.percent).toFixed(3)+"%";
    $("trafficBar").style.width=Math.min(100,Number(t.percent)||0)+"%";
    $("cpu").textContent=data.server.cpu+"%";$("load").textContent="负载 "+data.server.load.join(" / ");
    $("memory").textContent=data.server.memory.percent+"%";$("swap").textContent="Swap "+data.server.memory.swap_percent+"%";
    $("disk").textContent=data.server.disk.percent+"%";$("uptime").textContent="运行 "+duration(data.server.uptime);
    $("services").innerHTML=Object.entries(data.server.services).map(([name,status])=>`<span class="pill ${status==="active"?"ok":"bad"}">${esc(name)}：${esc(status)}</span>`).join("");
    $("users").innerHTML=data.users.map(user=>`<div class="card"><div class="head"><span class="name">${esc(user.username)}</span><span class="${user.online?"ok":"muted"}">${user.online?"在线 "+user.online+" 台":"离线"}</span></div><div class="stats"><div class="stat"><span class="label">月上传</span><b>${bytes(user.upload)}</b></div><div class="stat"><span class="label">月下载</span><b>${bytes(user.download)}</b></div><div class="stat"><span class="label">月合计</span><b>${bytes(user.total)}</b></div></div><div class="muted" style="margin-bottom:12px">速率模式：${esc(user.mode||"BBR 自动估速")} · 最后活动：${esc(user.last_active)} · 历史累计：${bytes(user.lifetime_total)}</div><div class="actions"><button class="btn primary" data-copy="${encodeURIComponent(user.subscription)}">复制订阅</button><button class="btn" data-copy="${encodeURIComponent(user.direct)}">复制基础直链</button><button class="btn" data-copy="${encodeURIComponent(user.password)}">复制密码</button></div></div>`).join("");
    document.querySelectorAll("[data-copy]").forEach(button=>{button.onclick=()=>copyText(decodeURIComponent(button.dataset.copy),button)});
    $("error").style.display=data.errors.length?"block":"none";$("error").textContent=data.errors.join("；");
  }catch(error){$("error").style.display="block";$("error").textContent="读取失败："+error.message}
}
load();setInterval(load,30000);
</script>
</body>
</html>
HTML

  chown -R root:caddy "$WEB_DIR"
  find "$WEB_DIR" -type d -exec chmod 0750 {} \;
  find "$WEB_DIR" -type f -exec chmod 0640 {} \;
}

write_systemd() {
  cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=HY2 AIO subscription, statistics and dashboard backend
After=network-online.target hysteria-server.service
Wants=network-online.target
Requires=hysteria-server.service

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/bin/python3 /usr/local/lib/hy2-aio/server.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=false

[Install]
WantedBy=multi-user.target
EOF
}

caddy_auth_directive() {
  local version major minor
  version="$(caddy version 2>/dev/null | sed -E 's/^v?([0-9]+)\.([0-9]+).*/\1 \2/' || true)"
  major="$(awk '{print $1}' <<<"$version")"
  minor="$(awk '{print $2}' <<<"$version")"
  if [ "${major:-2}" -gt 2 ] || { [ "${major:-2}" -eq 2 ] && [ "${minor:-6}" -ge 8 ]; }; then
    echo basic_auth
  else
    echo basicauth
  fi
}

write_caddy() {
  local hash auth
  hash="$(caddy hash-password --plaintext "$PANEL_PASS")"
  auth="$(caddy_auth_directive)"
  [ ! -f "$CADDY_FILE" ] || cp "$CADDY_FILE" "${CADDY_FILE}.before-hy2-aio-$(date +%Y%m%d-%H%M%S)"

  cat > "$CADDY_FILE" <<EOF
{
    servers {
        protocols h1 h2
    }
}

${DOMAIN}:${PANEL_PORT} {
    encode zstd gzip

    route {
        redir /${PANEL_PATH} /${PANEL_PATH}/ 308

        handle_path /${PANEL_PATH}/api/* {
            ${auth} {
                ${PANEL_USER} ${hash}
            }
            header {
                Cache-Control "no-store"
                X-Content-Type-Options "nosniff"
                X-Frame-Options "DENY"
                Referrer-Policy "no-referrer"
            }
            reverse_proxy 127.0.0.1:18081
        }

        handle_path /${PANEL_PATH}/* {
            ${auth} {
                ${PANEL_USER} ${hash}
            }
            header {
                Cache-Control "no-store, no-cache, must-revalidate"
                X-Content-Type-Options "nosniff"
                X-Frame-Options "DENY"
                Referrer-Policy "no-referrer"
            }
            root * ${WEB_DIR}
            file_server
        }

        handle /s/* {
            reverse_proxy 127.0.0.1:18081
        }

        handle {
            respond "Not Found" 404
        }
    }
}
EOF
  caddy fmt --overwrite "$CADDY_FILE"
  caddy validate --config "$CADDY_FILE"
}

generate_users() {
  local count="$1"
  python3 - "$count" "$USERS_FILE" <<'PY'
import json, os, secrets, sys
count = int(sys.argv[1])
path = sys.argv[2]
users = {}
for index in range(1, count + 1):
    users[f"user{index}"] = {
        "password": secrets.token_hex(16),
        "token": secrets.token_hex(24),
    }
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
  chmod 0640 "$USERS_FILE"
  chown root:hysteria "$USERS_FILE"
}

create_certificate() {
  install -d -o hysteria -g hysteria -m 0750 /etc/hysteria
  openssl req -x509 -nodes \
    -newkey ec \
    -pkeyopt ec_paramgen_curve:prime256v1 \
    -keyout "$HYSTERIA_KEY" \
    -out "$HYSTERIA_CERT" \
    -days 3650 \
    -subj "/CN=${PUBLIC_IP}" \
    -addext "subjectAltName=IP:${PUBLIC_IP}" >/dev/null 2>&1
  chown hysteria:hysteria "$HYSTERIA_CERT" "$HYSTERIA_KEY"
  chmod 0640 "$HYSTERIA_CERT"
  chmod 0600 "$HYSTERIA_KEY"
}

write_access_file() {
  read_env
  python3 - "$ENV_FILE" "$USERS_FILE" "$MODE_FILE" "$ACCESS_FILE" <<'PY'
import json, pathlib, sys, urllib.parse

env_file, users_file, mode_file, out_file = map(pathlib.Path, sys.argv[1:])
env = {}
for raw in env_file.read_text(encoding="utf-8").splitlines():
    raw = raw.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        env[key] = value

users = json.loads(users_file.read_text(encoding="utf-8"))
try:
    modes = json.loads(mode_file.read_text(encoding="utf-8"))
except Exception:
    modes = {"default": {"mode": "bbr"}, "users": {}}
if isinstance(modes, dict) and "mode" in modes:
    modes = {"default": modes, "users": {}}
if not isinstance(modes, dict):
    modes = {}
default_mode = modes.get("default", {"mode": "bbr"})
overrides = modes.get("users", {}) if isinstance(modes.get("users", {}), dict) else {}

def mode_label(value):
    if not isinstance(value, dict) or str(value.get("mode", "bbr")).lower() != "brutal":
        return "BBR 自动估速"
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return "BBR 自动估速"
    if up <= 0 or down <= 0:
        return "BBR 自动估速"
    return f"Brutal 上传 {up:g} / 下载 {down:g} Mbps"

lines = [
    "HY2 AIO 访问资料",
    "=" * 64,
    f"版本：{env.get('AIO_VERSION', '')}",
    f"服务器：{env['PUBLIC_IP']}",
    "端口：443/UDP",
    f"面板：https://{env['DOMAIN']}/{env['PANEL_PATH']}/",
    f"面板用户名：{env['PANEL_USER']}",
    f"面板密码：{env['PANEL_PASS']}",
    f"套餐总量（字节）：{env['TOTAL_BYTES']}",
    "",
]

for username, info in sorted(users.items()):
    password = str(info["password"])
    token = str(info["token"])
    subscription = f"https://{env['DOMAIN']}:{env.get('PANEL_PORT', '443')}/s/{token}"
    auth = urllib.parse.quote(f"{username}:{password}", safe="")
    query = urllib.parse.urlencode(
        {
            "insecure": "1",
            "obfs": "salamander",
            "obfs-password": env["OBFS_PASSWORD"],
            "sni": env.get("SNI", "www.amazon.sg"),
        }
    )
    node = urllib.parse.quote(f"HY2-{username}", safe="")
    direct = f"hysteria2://{auth}@{env['PUBLIC_IP']}:{env.get('HY2_PORT', '443')}/?{query}#{node}"
    lines.extend(
        [
            f"【{username}】",
            f"用户名：{username}",
            f"密码：{password}",
            f"速率模式：{mode_label(overrides.get(username, default_mode))}",
            f"Clash 订阅：{subscription}",
            f"HY2 基础直链（不含速率模式）：{direct}",
            "",
        ]
    )

out_file.write_text("\n".join(lines), encoding="utf-8")
PY
  chmod 0600 "$ACCESS_FILE"

  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    local user_home
    user_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    if [ -n "$user_home" ] && [ -d "$user_home" ]; then
      cp "$ACCESS_FILE" "$user_home/hy2-aio-access.txt"
      chown "$SUDO_USER":"$SUDO_USER" "$user_home/hy2-aio-access.txt" 2>/dev/null || true
      chmod 0600 "$user_home/hy2-aio-access.txt"
    fi
  fi
}

wait_services() {
  local service
  for service in hysteria-server.service hy2-aio.service caddy.service; do
    systemctl is-active --quiet "$service" || {
      journalctl -u "$service" --no-pager -n 80 >&2 || true
      die "服务启动失败：$service"
    }
  done
}

test_https() {
  local panel_url="https://${DOMAIN}:${PANEL_PORT}/${PANEL_PATH}/" code=""
  log "等待 HTTPS 证书与面板可用"
  for _ in $(seq 1 24); do
    code="$(curl -fsS -u "${PANEL_USER}:${PANEL_PASS}" \
      -o /dev/null -w '%{http_code}' \
      --connect-timeout 5 --max-time 12 "$panel_url" 2>/dev/null || true)"
    [ "$code" = "200" ] && break
    sleep 5
  done

  if [ "$code" != "200" ]; then
    warn "面板 HTTPS 暂未成功。请确认云厂商防火墙已放行 TCP 80、TCP 443、UDP 443。"
    warn "Caddy 日志：journalctl -u caddy -n 100 --no-pager"
  else
    log "HTTPS 面板测试成功：HTTP 200"
  fi
}

install_stack() {
  need_root install
  have_systemd || die "此脚本需要 systemd"
  [ -f /etc/os-release ] || die "无法识别系统"
  # shellcheck disable=SC1091
  source /etc/os-release
  detect_platform
  # The legacy Debian-only guard below is retained for compatibility; the
  # package adapter above is now the actual distribution gate.
  ID="debian"
  case "${ID:-}" in
    debian|ubuntu) ;;
    *) die "当前版本仅支持 Debian/Ubuntu，检测到：${ID:-unknown}" ;;
  esac

  if [ -f "$ENV_FILE" ] && [ "${HY2_FORCE:-0}" != "1" ]; then
    die "HY2 AIO 已安装。查看状态：sudo hy2ctl status"
  fi

  install_packages_v12

  PUBLIC_IP="${HY2_PUBLIC_IP:-$(detect_public_ipv4 || true)}"
  HY2_PORT="${HY2_PORT:-$(prompt_hysteria_port)}"
  PANEL_PORT="${HY2_PANEL_PORT:-$(prompt_panel_port)}"
  STATS_PORT="${HY2_STATS_PORT:-$(prompt_stats_port)}"
  [ -n "$PUBLIC_IP" ] || die "无法自动检测公网 IPv4，可使用 HY2_PUBLIC_IP=x.x.x.x 指定"

  NETWORK_INTERFACE="${HY2_INTERFACE:-$(detect_iface)}"
  [ -n "$NETWORK_INTERFACE" ] || die "无法检测默认网卡"

  local default_domain="${PUBLIC_IP//./-}.sslip.io"
  local users_count total_tb custom_domain
  users_count="${HY2_USERS:-$(prompt_value '创建用户数量' '5')}"
  [[ "$users_count" =~ ^[1-9][0-9]?$ ]] || die "用户数量必须是 1-99"

  total_tb="${HY2_TOTAL_TB:-$(prompt_value '套餐总流量 TB（十进制）' '1')}"
  if [ -n "${HY2_TOTAL_BYTES:-}" ]; then
    TOTAL_BYTES="$HY2_TOTAL_BYTES"
  else
    TOTAL_BYTES="$(python3 - "$total_tb" <<'PY'
from decimal import Decimal
import sys
try:
    value = Decimal(sys.argv[1])
    assert value > 0
except Exception:
    raise SystemExit(1)
print(int(value * Decimal(1_000_000_000_000)))
PY
)" || die "套餐流量格式错误"
  fi

  custom_domain="${HY2_DOMAIN:-$(prompt_value '订阅/面板域名（直接回车使用自动域名）' "$default_domain")}"
  DOMAIN="${custom_domain:-$default_domain}"
  PANEL_USER="${HY2_PANEL_USER:-admin}"
  PANEL_PASS="${HY2_PANEL_PASS:-$(rand_hex 12)}"
  PANEL_PATH="${HY2_PANEL_PATH:-hy2-$(rand_hex 12)}"
  OBFS_PASSWORD="$(rand_hex 16)"
  API_SECRET="$(rand_hex 24)"
  SNI="${HY2_SNI:-www.amazon.sg}"
  BACKUP_RETENTION_DAYS="${HY2_BACKUP_DAYS:-14}"

  python3 - "$PUBLIC_IP" <<'PYV' || die "公网 IPv4 格式错误：$PUBLIC_IP"
import ipaddress, sys
value = ipaddress.ip_address(sys.argv[1])
assert value.version == 4
PYV
  [[ "$NETWORK_INTERFACE" =~ ^[A-Za-z0-9_.:-]+$ ]] || die "网卡名称格式错误"
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || die "域名格式错误"
  [[ "$PANEL_USER" =~ ^[A-Za-z0-9_-]{1,32}$ ]] || die "面板用户名格式错误"
  [[ "$PANEL_PATH" =~ ^[A-Za-z0-9_-]{4,80}$ ]] || die "面板路径格式错误"
  [[ "$PANEL_PASS" =~ ^[A-Za-z0-9._-]{8,128}$ ]] || die "面板密码仅允许字母、数字、点、下划线、短横线，至少 8 位"
  [[ "$SNI" =~ ^[A-Za-z0-9.-]+$ ]] || die "SNI 格式错误"
  [[ "$TOTAL_BYTES" =~ ^[1-9][0-9]*$ ]] || die "TOTAL_BYTES 必须是正整数"

  log "公网 IPv4：$PUBLIC_IP"
  log "默认网卡：$NETWORK_INTERFACE"
  log "域名：$DOMAIN"
  log "用户数量：$users_count"
  log "套餐总量：$TOTAL_BYTES 字节"

  configure_swap_and_kernel
  install_hysteria
  install_caddy_v12

  getent group hysteria >/dev/null 2>&1 || groupadd --system hysteria
  id hysteria >/dev/null 2>&1 || useradd --system --gid hysteria --home /nonexistent --shell /usr/sbin/nologin hysteria

  install -d -o root -g hysteria -m 0750 "$CONFIG_DIR"
  install -d -o root -g root -m 0750 "$STATE_DIR" "$STATE_DIR/backups"
  install -d -o root -g root -m 0755 "$APP_DIR"

  cat > "$ENV_FILE" <<EOF
AIO_VERSION=$AIO_VERSION
PUBLIC_IP=$PUBLIC_IP
HY2_PORT=$HY2_PORT
PANEL_PORT=$PANEL_PORT
STATS_PORT=$STATS_PORT
DOMAIN=$DOMAIN
NETWORK_INTERFACE=$NETWORK_INTERFACE
TOTAL_BYTES=$TOTAL_BYTES
OBFS_PASSWORD=$OBFS_PASSWORD
API_SECRET=$API_SECRET
PANEL_PATH=$PANEL_PATH
PANEL_USER=$PANEL_USER
PANEL_PASS=$PANEL_PASS
SNI=$SNI
BACKUP_RETENTION_DAYS=$BACKUP_RETENTION_DAYS
EOF
  chown root:hysteria "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  configure_firewall_v12

  generate_users "$users_count"
  ensure_mode_file
  create_certificate
  write_rebuild_helper
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG"
  chmod 0640 "$HYSTERIA_CONFIG"

  write_backend
  write_panel
  write_systemd
  write_caddy
  write_access_file

  systemctl daemon-reload
  systemctl enable hysteria-server.service hy2-aio.service caddy.service >/dev/null
  systemctl restart hysteria-server.service
  sleep 2
  systemctl restart hy2-aio.service
  systemctl restart caddy.service
  sleep 3
  wait_services

  curl -fsS -X POST http://127.0.0.1:18081/sync >/dev/null || true

  local script_path
  script_path="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"
  install -m 0755 "$script_path" "$SELF_INSTALL"

  write_access_file
  test_https

  echo
  echo "============================================================"
  echo "HY2 AIO 安装完成"
  echo "============================================================"
  echo "面板：https://${DOMAIN}/${PANEL_PATH}/"
  echo "面板用户名：${PANEL_USER}"
  echo "面板密码：${PANEL_PASS}"
  echo "账号资料：${ACCESS_FILE}"
  echo
  echo "常用命令："
  echo "  sudo hy2ctl status"
  echo "  sudo hy2ctl show"
  echo "  sudo hy2ctl sync"
  echo "  sudo hy2ctl mode"
  echo "  sudo hy2ctl add-user 用户名"
  echo "  sudo hy2ctl remove-user 用户名"
  echo "  sudo hy2ctl rotate-user 用户名"
  echo "  sudo hy2ctl backup"
  echo
  echo "云厂商防火墙必须放行：TCP 80、TCP 443、UDP 443"
  echo "============================================================"
}

snapshot_before_change() {
  install -d -m 0700 "$STATE_DIR/rollbacks"
  local snapshot="$STATE_DIR/rollbacks/hy2-before-$(date +%Y%m%d-%H%M%S).tar.gz"
  tar -czf "$snapshot" --ignore-failed-read \
    "$CONFIG_DIR" /etc/hysteria "$APP_DIR" "$WEB_DIR" "$CADDY_FILE" \
    "$SERVICE_FILE" /etc/systemd/system/hysteria-server.service
  chmod 600 "$snapshot"
  printf '%s\n' "$snapshot"
}

rollback_cmd() {
  need_root rollback
  read_env
  local snapshot
  snapshot="$(find "$STATE_DIR/rollbacks" -maxdepth 1 -type f -name 'hy2-before-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | sed -n '1s/^[^ ]* //p')"
  [ -n "$snapshot" ] || die "No rollback snapshot found"
  echo "Latest snapshot: $snapshot"
  echo "0. Restore"
  echo "1. Cancel"
  local choice
  read -r -p "Choose [0/1]: " choice
  [ "$choice" = "0" ] || return 0
  tar -xzf "$snapshot" -C /
  systemctl daemon-reload
  systemctl restart hysteria-server.service hy2-aio.service caddy.service || true
  log "Rollback complete"
}

repair_cmd() {
  need_root repair
  read_env
  log "Rollback snapshot: $(snapshot_before_change)"

  log "升级/修复 HY2 AIO 管理组件"
  ensure_mode_file

  python3 - "$ENV_FILE" "$SCRIPT_VERSION" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
found = False
output = []
for line in lines:
    if line.startswith("AIO_VERSION="):
        output.append(f"AIO_VERSION={version}")
        found = True
    else:
        output.append(line)
if not found:
    output.insert(0, f"AIO_VERSION={version}")
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
os.replace(temporary, path)
PY
  chown root:hysteria "$ENV_FILE"
  chmod 0640 "$ENV_FILE"

  write_backend
  write_panel
  write_systemd
  systemctl daemon-reload
  systemctl enable hy2-aio.service >/dev/null

  if ! systemctl restart hy2-aio.service; then
    journalctl -u hy2-aio.service --no-pager -n 100 >&2 || true
    die "HY2 AIO 后端升级失败"
  fi

  sleep 2
  systemctl is-active --quiet hy2-aio.service || die "HY2 AIO 后端未运行"
  api_post sync >/dev/null || true

  local script_path
  script_path="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"
  install -m 0755 "$script_path" "$SELF_INSTALL"
  write_access_file

  log "HY2 AIO 已升级到 v${SCRIPT_VERSION}"
  log "Hysteria 服务未重启，当前连接不会因本次升级中断"
  echo "运行速率模式菜单：sudo hy2ctl mode"
}

manual_hy2_detected() {
  pgrep -f '/hysteria([[:space:]]|$).*server' >/dev/null 2>&1 && return 0
  [ -f /etc/hysteria/config.yaml ] && return 0
  return 1
}

auto_cmd() {
  need_root auto

  if [ ! -f "$SERVICE_FILE" ]; then
    if manual_hy2_detected; then
      echo
      echo "Existing manual Hysteria deployment detected."
      echo "0. Install AIO anyway (choose a free UDP port)"
      echo "1. Keep the existing deployment and exit"
      if [ ! -t 0 ]; then
        warn "Non-interactive mode: existing deployment was left untouched"
        return 1
      fi
      local choice
      read -r -p "Choose [0/1]: " choice || choice="1"
      [ "$choice" = "0" ] || { log "Existing deployment left untouched"; return; }
    fi
    install_stack
    return
  fi

  local problems=()
  [ -f "$ENV_FILE" ] || problems+=("missing $ENV_FILE")
  [ -f "$APP_FILE" ] || problems+=("missing $APP_FILE")
  systemctl is-active --quiet hy2-aio.service || problems+=("hy2-aio.service is not active")
  [ ! -f "$APP_FILE" ] || grep -q 'proxy-groups:' "$APP_FILE" || problems+=("GLOBAL group missing")

  if [ "${#problems[@]}" -eq 0 ]; then
    log "HY2 AIO is healthy; no repair is needed"
    return
  fi

  echo "Problems detected:"
  printf '  - %s\n' "${problems[@]}"
  echo "0. Repair"
  echo "1. Do not repair"
  [ -t 0 ] || { warn "Use ssh -t to choose repair"; return 1; }
  local choice
  read -r -p "Choose [0/1]: " choice || choice="1"
  [ "$choice" = "0" ] && repair_cmd || log "Repair skipped"
}

status_cmd() {
  need_root status
  read_env
  echo "HY2 AIO v${AIO_VERSION:-unknown}"
  echo "面板：https://${DOMAIN}/${PANEL_PATH}/"
  echo
  systemctl --no-pager --full status \
    hysteria-server.service hy2-aio.service caddy.service \
    | sed -n '1,45p' || true
  echo
  ss -lntup | grep -E ':(80|443|18081|9999)\b' || true
}

show_cmd() {
  need_root show
  read_env
  write_access_file
  cat "$ACCESS_FILE"
}

sync_cmd() {
  need_root sync
  read_env
  api_post sync
  echo
}

backup_cmd() {
  need_root backup
  read_env
  api_post backup
  echo
}

logs_cmd() {
  need_root logs
  journalctl -u hysteria-server.service -u hy2-aio.service -u caddy.service \
    --no-pager -n "${2:-120}"
}

restart_cmd() {
  need_root restart
  systemctl restart hysteria-server.service hy2-aio.service caddy.service
  sleep 2
  status_cmd
}

modify_user() {
  local action="$1" username="${2:-}"
  need_root "$action"
  read_env
  valid_name "$username" || die "用户名仅允许字母、数字、下划线、短横线，长度 1-32"

  cp "$USERS_FILE" "${USERS_FILE}.bak"
  case "$action" in
    add-user)
      python3 - "$USERS_FILE" "$username" <<'PY'
import json, os, secrets, sys
path, username = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username in users:
    raise SystemExit("用户已存在")
users[username] = {"password": secrets.token_hex(16), "token": secrets.token_hex(24)}
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    remove-user)
      python3 - "$USERS_FILE" "$username" <<'PY'
import json, os, sys
path, username = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username not in users:
    raise SystemExit("用户不存在")
if len(users) <= 1:
    raise SystemExit("不能删除最后一个用户")
del users[username]
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    rotate-user)
      python3 - "$USERS_FILE" "$username" <<'PY'
import json, os, secrets, sys
path, username = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username not in users:
    raise SystemExit("用户不存在")
users[username]["password"] = secrets.token_hex(16)
users[username]["token"] = secrets.token_hex(24)
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    *) die "未知用户操作：$action" ;;
  esac

  chown root:hysteria "$USERS_FILE"
  chmod 0640 "$USERS_FILE"
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG"
  chmod 0640 "$HYSTERIA_CONFIG"

  if ! systemctl restart hysteria-server.service; then
    warn "Hysteria 重启失败，恢复用户配置"
    mv "${USERS_FILE}.bak" "$USERS_FILE"
    "$REBUILD_FILE"
    systemctl restart hysteria-server.service || true
    die "修改失败"
  fi
  rm -f "${USERS_FILE}.bak"
  systemctl restart hy2-aio.service
  sleep 2
  api_post sync >/dev/null || true
  write_access_file
  log "用户操作完成：$action $username"
  show_cmd
}

mode_show_plain() {
  python3 - "$MODE_FILE" "$USERS_FILE" <<'PY'
import json
import sys
from pathlib import Path

mode_path = Path(sys.argv[1])
users_path = Path(sys.argv[2])

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def normalize(value):
    if not isinstance(value, dict) or str(value.get("mode", "bbr")).lower() != "brutal":
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    if up <= 0 or down <= 0:
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    return {"mode": "brutal", "up_mbps": up, "down_mbps": down}

def label(value):
    item = normalize(value)
    if item["mode"] != "brutal":
        return "BBR 自动估速"
    return f'Brutal 上传 {item["up_mbps"]:g} / 下载 {item["down_mbps"]:g} Mbps'

data = load(mode_path, {})
users = load(users_path, {})
if isinstance(data, dict) and "mode" in data:
    data = {"default": normalize(data), "users": {}}
if not isinstance(data, dict):
    data = {}
default = normalize(data.get("default", {}))
overrides = data.get("users", {}) if isinstance(data.get("users", {}), dict) else {}

print(f"全局默认：{label(default)}")
print("用户实际模式：")
for username in sorted(users):
    if username in overrides:
        print(f"  {username}: {label(overrides[username])}（单独设置）")
    else:
        print(f"  {username}: {label(default)}（继承默认）")
PY
}

mode_apply() {
  local scope="$1" target="$2" mode="$3" up="${4:-0}" down="${5:-0}"
  local backup="${MODE_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  cp -a "$MODE_FILE" "$backup"

  if ! python3 - "$MODE_FILE" "$USERS_FILE" "$scope" "$target" "$mode" "$up" "$down" <<'PY'
import json
import os
import sys
from pathlib import Path

mode_path = Path(sys.argv[1])
users_path = Path(sys.argv[2])
scope = sys.argv[3]
target = sys.argv[4]
mode = sys.argv[5].lower()

try:
    users = json.loads(users_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit("users.json 读取失败")

try:
    data = json.loads(mode_path.read_text(encoding="utf-8"))
except Exception:
    data = {"default": {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}, "users": {}}

if isinstance(data, dict) and "mode" in data:
    data = {"default": data, "users": {}}
if not isinstance(data, dict):
    data = {}
data.setdefault("default", {"mode": "bbr", "up_mbps": 0, "down_mbps": 0})
data.setdefault("users", {})
if not isinstance(data["users"], dict):
    data["users"] = {}

if scope == "user" and target not in users:
    raise SystemExit(f"用户不存在：{target}")

if mode == "inherit":
    if scope != "user":
        raise SystemExit("只有单个用户可以恢复继承默认")
    data["users"].pop(target, None)
else:
    if mode == "brutal":
        try:
            up_value = float(sys.argv[6])
            down_value = float(sys.argv[7])
        except ValueError:
            raise SystemExit("上传和下载必须是数字")
        if up_value <= 0 or down_value <= 0:
            raise SystemExit("Brutal 上传和下载必须大于 0")
        if up_value > 2000 or down_value > 2000:
            raise SystemExit("单项最高允许 2000 Mbps")
        value = {"mode": "brutal", "up_mbps": up_value, "down_mbps": down_value}
    else:
        value = {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}

    if scope == "default":
        data["default"] = value
    else:
        data["users"][target] = value

temporary = mode_path.with_suffix(mode_path.suffix + ".tmp")
temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temporary, mode_path)
PY
  then
    rm -f "$backup"
    die "速率模式写入失败"
  fi

  chown root:hysteria "$MODE_FILE"
  chmod 0640 "$MODE_FILE"

  if ! systemctl restart hy2-aio.service; then
    warn "订阅后端重启失败，恢复上一份模式配置"
    mv "$backup" "$MODE_FILE"
    chown root:hysteria "$MODE_FILE"
    chmod 0640 "$MODE_FILE"
    systemctl restart hy2-aio.service || true
    die "模式切换失败"
  fi

  rm -f "$backup"
  sleep 2
  api_post sync >/dev/null || true
  write_access_file
  echo
  mode_show_plain
  echo
  echo "已更新 Clash 订阅；Hysteria 服务未重启。"
  echo "请在客户端刷新订阅并重新选择节点。"
}

mode_apply_preset() {
  local scope="$1" target="$2" preset="$3"
  case "$preset" in
    bbr|auto|1) mode_apply "$scope" "$target" bbr 0 0 ;;
    30|2) mode_apply "$scope" "$target" brutal 10 30 ;;
    50|3) mode_apply "$scope" "$target" brutal 15 50 ;;
    80|4) mode_apply "$scope" "$target" brutal 20 80 ;;
    120|5) mode_apply "$scope" "$target" brutal 30 120 ;;
    200|6) mode_apply "$scope" "$target" brutal 50 200 ;;
    300|7) mode_apply "$scope" "$target" brutal 80 300 ;;
    inherit|9) mode_apply "$scope" "$target" inherit 0 0 ;;
    *) return 1 ;;
  esac
}

mode_menu_presets() {
  local allow_inherit="${1:-0}"
  echo
  echo "1. BBR 自动估速"
  echo "2. Brutal 上传 10 / 下载 30 Mbps（下载理论 3.75 MB/s）"
  echo "3. Brutal 上传 15 / 下载 50 Mbps（下载理论 6.25 MB/s）"
  echo "4. Brutal 上传 20 / 下载 80 Mbps（下载理论 10 MB/s）"
  echo "5. Brutal 上传 30 / 下载 120 Mbps（下载理论 15 MB/s）"
  echo "6. Brutal 上传 50 / 下载 200 Mbps（下载理论 25 MB/s）"
  echo "7. Brutal 上传 80 / 下载 300 Mbps（下载理论 37.5 MB/s）"
  echo "8. 自定义 Mbps"
  [ "$allow_inherit" = "1" ] && echo "9. 恢复继承全局默认"
  echo "0. 退出"
}

mode_interactive() {
  echo "============================================================"
  echo "HY2 客户端速率模式"
  echo "============================================================"
  mode_show_plain
  echo
  echo "1. 修改全局默认（所有未单独设置的用户）"
  echo "2. 修改单个用户"
  echo "0. 退出"
  echo
  read -r -p "请选择目标：" target_choice

  local scope target allow_inherit=0
  case "$target_choice" in
    0) return 0 ;;
    1) scope="default"; target="default" ;;
    2)
      scope="user"
      allow_inherit=1
      echo "现有用户：$(python3 - "$USERS_FILE" <<'PY'
import json, sys
print(" ".join(sorted(json.load(open(sys.argv[1], encoding="utf-8")))))
PY
)"
      read -r -p "请输入用户名：" target
      valid_name "$target" || die "用户名格式错误"
      ;;
    *) die "输入无效" ;;
  esac

  mode_menu_presets "$allow_inherit"
  echo
  read -r -p "请输入数字：" preset
  [ "$preset" = "0" ] && return 0

  if [ "$preset" = "8" ]; then
    local up down
    read -r -p "上传目标 Mbps：" up
    read -r -p "下载目标 Mbps：" down
    mode_apply "$scope" "$target" brutal "$up" "$down"
    return
  fi

  mode_apply_preset "$scope" "$target" "$preset" || die "输入无效"
}

mode_cmd() {
  need_root mode
  read_env
  ensure_mode_file

  local target="${2:-}" preset="${3:-}"
  if [ -z "$target" ]; then
    mode_interactive
    return
  fi

  if [ "$target" = "show" ]; then
    mode_show_plain
    return
  fi

  local scope
  if [ "$target" = "default" ]; then
    scope="default"
  else
    scope="user"
    valid_name "$target" || die "用户名格式错误"
  fi

  [ -n "$preset" ] || die "缺少模式。示例：sudo hy2ctl mode $target 80"

  if [ "$preset" = "custom" ]; then
    [ "$#" -eq 5 ] || die "用法：sudo hy2ctl mode $target custom 上传Mbps 下载Mbps"
    mode_apply "$scope" "$target" brutal "$4" "$5"
    return
  fi

  mode_apply_preset "$scope" "$target" "$preset" || die "未知模式：$preset"
}

users_cmd() {
  need_root users
  read_env
  python3 - "$USERS_FILE" "$STATE_DIR/state.json" <<'PY'
import json, sys
users = json.load(open(sys.argv[1], encoding="utf-8"))
try:
    state = json.load(open(sys.argv[2], encoding="utf-8"))
except Exception:
    state = {}
stats = state.get("users", {})
print(f"{'用户':<18} {'月流量(MB)':>14} {'历史累计(MB)':>16}")
print("-" * 52)
for name in sorted(users):
    item = stats.get(name, {})
    month = int(item.get("month_tx", 0)) + int(item.get("month_rx", 0))
    total = int(item.get("lifetime_tx", 0)) + int(item.get("lifetime_rx", 0))
    print(f"{name:<18} {month/1_000_000:>14.2f} {total/1_000_000:>16.2f}")
PY
}

update_cmd() {
  need_root update
  log "升级 Hysteria 2"
  bash <(curl -fsSL https://get.hy2.sh/)
  systemctl restart hysteria-server.service
  hysteria version || true
}

uninstall_cmd() {
  need_root uninstall
  read_env
  local answer="${HY2_YES:-}"
  if [ "$answer" != "1" ]; then
    read -r -p "确认卸载 HY2 AIO 服务？输入 YES：" answer
    [ "$answer" = "YES" ] || die "已取消"
  fi

  api_post backup >/dev/null 2>&1 || true
  systemctl disable --now hy2-aio.service hysteria-server.service 2>/dev/null || true
  rm -f "$SERVICE_FILE" "$SELF_INSTALL"
  rm -rf "$APP_DIR" "$WEB_DIR"
  systemctl daemon-reload
  warn "保留配置与数据目录：$CONFIG_DIR、$STATE_DIR、/etc/hysteria"
  warn "Caddy 软件未卸载；Caddyfile 仍在 $CADDY_FILE"
}

usage() {
  cat <<EOF
HY2 AIO v${AIO_VERSION}

用法：
  sudo bash hy2-aio.sh install
  sudo hy2ctl status
  sudo hy2ctl show
  sudo hy2ctl sync
  sudo hy2ctl mode
  sudo hy2ctl mode show
  sudo hy2ctl users
  sudo hy2ctl add-user <用户名>
  sudo hy2ctl remove-user <用户名>
  sudo hy2ctl rotate-user <用户名>
  sudo hy2ctl backup
  sudo hy2ctl logs [行数]
  sudo hy2ctl restart
  sudo bash hy2-aio.sh repair
  sudo hy2ctl update
  sudo hy2ctl uninstall

无人值守安装：
  sudo HY2_NONINTERACTIVE=1 HY2_USERS=5 HY2_TOTAL_TB=1 bash hy2-aio.sh install

可选环境变量：
  HY2_PUBLIC_IP       手动指定公网 IPv4
  HY2_INTERFACE       手动指定网卡
  HY2_DOMAIN          自定义域名（必须已解析到服务器）
  HY2_USERS           用户数量，默认 5
  HY2_TOTAL_TB        十进制 TB，默认 1
  HY2_TOTAL_BYTES     直接指定字节数
  HY2_PANEL_USER      面板用户名，默认 admin
  HY2_PANEL_PASS      面板密码
  HY2_PANEL_PATH      面板随机路径
  HY2_SNI             客户端 SNI，默认 www.amazon.sg
  HY2_BACKUP_DAYS     备份保留天数，默认 14
EOF
}

command_name="${1:-auto}"
case "$command_name" in
  auto) auto_cmd ;;
  install) install_stack ;;
  repair|upgrade-aio) repair_cmd ;;
  status) status_cmd ;;
  show) show_cmd ;;
  sync) sync_cmd ;;
  mode) mode_cmd "$@" ;;
  backup) backup_cmd ;;
  rollback) rollback_cmd ;;
  logs) logs_cmd "$@" ;;
  restart) restart_cmd ;;
  users) users_cmd ;;
  add-user|remove-user|rotate-user) modify_user "$command_name" "${2:-}" ;;
  update) update_cmd ;;
  uninstall) uninstall_cmd ;;
  help|-h|--help) usage ;;
  *) usage; exit 1 ;;
esac
