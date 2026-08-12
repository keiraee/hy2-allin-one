#!/usr/bin/env bash
# core.sh - 基础工具函数

set -Eeuo pipefail

SCRIPT_VERSION="1.3.5"
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
SELF_INSTALL="/usr/local/sbin/hy2"

log() { printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

need_root() {
  [ "$(id -u)" -eq 0 ] || die "请使用 root 运行：sudo hy2 ${1:-install}"
}

have_systemd() {
  command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

PKG_MANAGER=""

detect_platform() {
  have_systemd || die "此脚本需要 systemd"
  [ -r /etc/os-release ] || die "无法检测 Linux 发行版"
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
    die "不支持的包管理器：${PRETTY_NAME:-unknown}"
  fi
  log "检测到 ${PRETTY_NAME:-unknown}；包管理器：$PKG_MANAGER"
}

rand_hex() { openssl rand -hex "${1:-16}"; }
valid_name() { [[ "${1:-}" =~ ^[A-Za-z0-9_-]{1,32}$ ]]; }

read_env() {
  [ -f "$ENV_FILE" ] || die "尚未安装。请运行：sudo hy2 install"
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -z "$line" ] && continue
    case "$line" in
      \#*) continue ;;
    esac
    case "$line" in
      *=*) ;;
      *) die "config.env 含非法行：$line" ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "config.env 含非法键名：$key"
    printf -v "$key" '%s' "$value"
    export "$key"
  done < "$ENV_FILE"
  HY2_PORT="${HY2_PORT:-443}"
  PANEL_PORT="${PANEL_PORT:-443}"
  STATS_PORT="${STATS_PORT:-9999}"
}

api_post() {
  : "${API_SECRET:?API_SECRET 未设置，请先 read_env}"
  curl -fsS --connect-timeout 5 --max-time 60 \
    -H "X-API-Secret: ${API_SECRET}" \
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
      warn "端口必须是 1-65535 的整数"
      value=""
      continue
    }
    if tcp_port_is_used "$value"; then
      warn "TCP 端口 $value 已被占用"
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
      warn "端口必须是 1-65535 的整数"
      value=""
      continue
    }
    if tcp_port_is_used "$value"; then
      warn "TCP 端口 $value 已被占用"
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
      warn "端口必须是 1-65535 的整数"
      value=""
      continue
    }
    if port_is_used "$value"; then
      warn "UDP 端口 $value 已被占用"
      value=""
      continue
    fi
    printf '%s' "$value"
    return
  done
}
