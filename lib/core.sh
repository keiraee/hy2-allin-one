#!/usr/bin/env bash
# core.sh - 基础工具函数

set -Eeuo pipefail

SCRIPT_VERSION="1.3.22"
AIO_VERSION="$SCRIPT_VERSION"
CONFIG_DIR="/etc/hy2-aio"
HYSTERIA_DIR="/etc/hysteria"
ENV_FILE="${CONFIG_DIR}/config.env"
USERS_FILE="${CONFIG_DIR}/users.json"
USER_MUTATION_LOCK="${CONFIG_DIR}/.users.lock"
readonly USER_MUTATION_LOCK
MODE_FILE="${CONFIG_DIR}/client-mode.json"
HYSTERIA_CONFIG="/etc/hysteria/config.yaml"
HYSTERIA_CERT="/etc/hysteria/server.crt"
HYSTERIA_KEY="/etc/hysteria/server.key"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="18081"
readonly BACKEND_HOST BACKEND_PORT
APP_DIR="/usr/local/lib/hy2-aio"
APP_FILE="${APP_DIR}/server.py"
REBUILD_FILE="${APP_DIR}/rebuild_config.py"
WEB_DIR="/var/www/hy2-aio"
STATE_DIR="/var/lib/hy2-aio"
ROLLBACK_DIR="/var/lib/hy2-aio-rollbacks"
readonly ROLLBACK_DIR
ACCESS_FILE="/root/hy2-aio-access.txt"
CADDY_FILE="/etc/caddy/Caddyfile"
CADDY_SITE_FILE="/etc/caddy/hy2-aio.caddy"
SERVICE_FILE="/etc/systemd/system/hy2-aio.service"
HYSTERIA_SERVICE_FILE="/etc/systemd/system/hysteria-server.service"
RELOAD_PATH_FILE="/etc/systemd/system/hy2-aio-reload-hysteria.path"
RELOAD_SERVICE_FILE="/etc/systemd/system/hy2-aio-reload-hysteria.service"
SELF_INSTALL="/usr/local/bin/hy2"
SELF_INSTALL_SBIN="/usr/local/sbin/hy2"

log() { printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "需要 root。已是 root：hy2 ${1:-}；有 sudo：sudo hy2 ${1:-}"
  fi
}

install_hy2_cli() {
  local src="${1:-}"
  [ -n "$src" ] && [ -f "$src" ] || die "install_hy2_cli：缺少源文件"
  install -d -m 0755 /usr/local/bin /usr/local/sbin
  install -m 0755 "$src" "$SELF_INSTALL"
  ln -sfn "$SELF_INSTALL" "$SELF_INSTALL_SBIN"
}

remove_hy2_cli() {
  rm -f "$SELF_INSTALL" "$SELF_INSTALL_SBIN"
}

ensure_hysteria_config_perms() {
  install -d -o hysteria -g hysteria -m 2770 /etc/hysteria 2>/dev/null || true
  # Backend (hy2-aio) must create users.json.tmp here.
  install -d -o root -g hy2-aio -m 0770 "$CONFIG_DIR" 2>/dev/null || true
  chown root:hy2-aio "$CONFIG_DIR" 2>/dev/null || true
  chmod 0770 "$CONFIG_DIR" 2>/dev/null || true
  touch "$USER_MUTATION_LOCK" 2>/dev/null || true
  chown hy2-aio:hy2-aio "$USER_MUTATION_LOCK" 2>/dev/null || true
  chmod 0660 "$USER_MUTATION_LOCK" 2>/dev/null || true
  if [ -f "$USERS_FILE" ]; then
    chown hy2-aio:hy2-aio "$USERS_FILE" 2>/dev/null || true
    chmod 0640 "$USERS_FILE" 2>/dev/null || true
  fi
  if [ -f "$HYSTERIA_CONFIG" ]; then
    chown hysteria:hysteria "$HYSTERIA_CONFIG" 2>/dev/null || true
    chmod 0660 "$HYSTERIA_CONFIG" 2>/dev/null || true
  fi
  if [ -f "${HYSTERIA_CERT:-}" ]; then
    chown hysteria:hysteria "$HYSTERIA_CERT" "$HYSTERIA_KEY" 2>/dev/null || true
    chmod 0640 "$HYSTERIA_CERT" 2>/dev/null || true
    chmod 0640 "$HYSTERIA_KEY" 2>/dev/null || true
  fi
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
panel_port_is_valid() {
  local value="${1:-}"
  [[ "$value" =~ ^[0-9]+$ ]] \
    && [ "$value" -ge 1 ] \
    && [ "$value" -le 65535 ] \
    && [ "$value" -ne 80 ]
}

port_number_is_valid() {
  local value="${1:-}"
  [[ "$value" =~ ^[0-9]+$ ]] \
    && [ "$value" -ge 1 ] \
    && [ "$value" -le 65535 ]
}

port_layout_is_valid() {
  local panel_port="${1:-}" stats_port="${2:-}"
  panel_port_is_valid "$panel_port" \
    && port_number_is_valid "$stats_port" \
    && [ "$panel_port" -ne "$stats_port" ] \
    && [ "$panel_port" -ne "$BACKEND_PORT" ] \
    && [ "$stats_port" -ne "$BACKEND_PORT" ]
}

validate_port_layout() {
  local panel_port="${1:-}" stats_port="${2:-}"
  panel_port_is_valid "$panel_port" \
    || die "面板端口 ${panel_port:-<empty>} 无效或不安全；管理面板仅支持 HTTPS，禁止使用 80"
  port_number_is_valid "$stats_port" \
    || die "统计端口 ${stats_port:-<empty>} 无效；必须是 1-65535 的整数"
  [ "$panel_port" -ne "$stats_port" ] \
    || die "端口冲突：面板端口与统计端口不能同为 $panel_port"
  [ "$panel_port" -ne "$BACKEND_PORT" ] \
    || die "端口冲突：面板端口不能使用内部后端端口 $BACKEND_PORT"
  [ "$stats_port" -ne "$BACKEND_PORT" ] \
    || die "端口冲突：统计端口不能使用内部后端端口 $BACKEND_PORT"
}

read_env() {
  [ -f "$ENV_FILE" ] || die "尚未安装。请以 root 运行：bash hy2.sh install"
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
  validate_port_layout "$PANEL_PORT" "$STATS_PORT"
  OBFS_ENABLED="${OBFS_ENABLED:-true}"
  QUIC_KEEP_ALIVE_PERIOD="${QUIC_KEEP_ALIVE_PERIOD:-5s}"
  QUIC_MAX_IDLE_TIMEOUT="${QUIC_MAX_IDLE_TIMEOUT:-120s}"
}

api_post() {
  : "${API_SECRET:?API_SECRET 未设置，请先 read_env}"
  curl -fsS --connect-timeout 5 --max-time 60 \
    -H "X-API-Secret: ${API_SECRET}" \
    -X POST "http://${BACKEND_HOST}:${BACKEND_PORT}/$1"
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
  ss -Hlunp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" || $4 ~ p" " {found=1} END {exit !found}'
}

tcp_port_is_used() {
  local port="$1"
  ss -Hlntp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" || $4 ~ p" " {found=1} END {exit !found}'
}

ensure_install_ports_available() {
  local hy2_port="$1" panel_port="$2" stats_port="$3"
  validate_port_layout "$panel_port" "$stats_port"
  port_is_used "$hy2_port" \
    && die "代理 UDP 端口 $hy2_port 已被占用"
  tcp_port_is_used "$panel_port" \
    && die "面板 TCP 端口 $panel_port 已被占用"
  tcp_port_is_used "$stats_port" \
    && die "统计 TCP 端口 $stats_port 已被占用"
  tcp_port_is_used "$BACKEND_PORT" \
    && die "内部后端 TCP 端口 $BACKEND_PORT 已被占用"
  return 0
}

prompt_panel_port() {
  local value="${HY2_PANEL_PORT:-}" default="443"
  while true; do
    if [ -z "$value" ]; then
      value="$(prompt_value '面板 HTTPS 端口（一般不用改）' "$default")"
    fi
    [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || {
      warn "端口必须是 1-65535 的整数"
      value=""
      continue
    }
    if [ "$value" -eq 80 ]; then
      warn "管理面板仅支持 HTTPS，不能使用端口 80"
      value=""
      continue
    fi
    if tcp_port_is_used "$value"; then
      warn "TCP 端口 $value 已被占用，请换一个"
      value=""
      continue
    fi
    printf '%s' "$value"
    return
  done
}

prompt_stats_port() {
  local value="${HY2_STATS_PORT:-}" default="9999"
  # 小白安装不询问；无人值守/显式环境变量才用自定义
  if [ -z "$value" ]; then
    printf '%s' "$default"
    return
  fi
  while true; do
    [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || {
      die "HY2_STATS_PORT 须为 1-65535 的整数"
    }
    if tcp_port_is_used "$value"; then
      die "内部统计端口 TCP $value 已被占用"
    fi
    printf '%s' "$value"
    return
  done
}

prompt_hysteria_port() {
  # 默认 8443：云上 UDP 443 更容易被干扰；仍可手动改成 443
  local value="${HY2_PORT:-}" default="8443"
  while true; do
    if [ -z "$value" ]; then
      if [ -t 0 ] && [ "${HY2_NONINTERACTIVE:-0}" != "1" ]; then
        echo "  提示：AWS/GCP 等云服务器建议用 8443；也可改成 443" >&2
      fi
      value="$(prompt_value '代理 UDP 端口' "$default")"
    fi
    [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || {
      warn "端口必须是 1-65535 的整数"
      value=""
      continue
    }
    if port_is_used "$value"; then
      warn "UDP 端口 $value 已被占用，请换一个"
      value=""
      continue
    fi
    printf '%s' "$value"
    return
  done
}
