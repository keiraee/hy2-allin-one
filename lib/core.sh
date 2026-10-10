#!/usr/bin/env bash
# core.sh - 基础工具函数

set -Eeuo pipefail

SCRIPT_VERSION="1.7.2"
AIO_VERSION="$SCRIPT_VERSION"
XRAY_VERSION="v26.3.27"
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
XRAY_BIN="/usr/local/bin/xray"
HYSTERIA_BIN="/usr/local/bin/hysteria"
CADDY_BIN="/usr/local/bin/caddy"
CADDY_SERVICE_FILE="/etc/systemd/system/caddy.service"
CADDY_APT_LIST="/etc/apt/sources.list.d/caddy-stable.list"
CADDY_APT_KEYRING="/usr/share/keyrings/caddy-stable-archive-keyring.gpg"
CADDY_DIR="/etc/caddy"
CADDY_DATA_DIR="/var/lib/caddy"
CADDY_LOG_DIR="/var/log/caddy"
XRAY_CONFIG="${CONFIG_DIR}/xray.json"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="18081"
readonly BACKEND_HOST BACKEND_PORT
APP_DIR="/usr/local/lib/hy2-aio"
APP_FILE="${APP_DIR}/server.py"
REBUILD_FILE="${APP_DIR}/rebuild_config.py"
XRAY_REBUILD_FILE="${APP_DIR}/rebuild_xray.py"
WEB_DIR="/var/www/hy2-aio"
STATE_DIR="/var/lib/hy2-aio"
ROLLBACK_DIR="/var/lib/hy2-aio-rollbacks"
readonly ROLLBACK_DIR
ACCESS_FILE="/root/hy2-aio-access.txt"
CADDY_FILE="/etc/caddy/Caddyfile"
CADDY_SITE_FILE="/etc/caddy/hy2-aio.caddy"
SERVICE_FILE="/etc/systemd/system/hy2-aio.service"
HYSTERIA_SERVICE_FILE="/etc/systemd/system/hysteria-server.service"
XRAY_SERVICE_FILE="/etc/systemd/system/hy2-xray.service"
RELOAD_PATH_FILE="/etc/systemd/system/hy2-aio-reload-hysteria.path"
RELOAD_SERVICE_FILE="/etc/systemd/system/hy2-aio-reload-hysteria.service"
XRAY_RELOAD_PATH_FILE="/etc/systemd/system/hy2-aio-reload-xray.path"
XRAY_RELOAD_SERVICE_FILE="/etc/systemd/system/hy2-aio-reload-xray.service"
HYSTERIA_CONTROL_FILE="${APP_DIR}/hysteria-control.sh"
XRAY_CONTROL_FILE="${APP_DIR}/xray-control.sh"
XRAY_PRESTART_FILE="${APP_DIR}/xray-prestart.sh"
HYSTERIA_DROPIN_DIR="/etc/systemd/system/hysteria-server.service.d"
HYSTERIA_DROPIN_FILE="${HYSTERIA_DROPIN_DIR}/hy2-switch.conf"
HY2_OFF_FILE="${CONFIG_DIR}/hy2.off"
HYSTERIA_CMD_FILE="/run/hy2-aio/hysteria-cmd"
HYSTERIA_RELOAD_FLAG="/run/hy2-aio/reload-hysteria"
XRAY_CMD_FILE="/run/hy2-aio/xray-cmd"
XRAY_RELOAD_FLAG="/run/hy2-aio/reload-xray"
REALITY_DEST_DEFAULT="www.cloudflare.com:443"
SELF_INSTALL="/usr/local/bin/hy2"
SELF_INSTALL_SBIN="/usr/local/sbin/hy2"

log() { printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

print_welcome_banner() {
  printf '\033[1;36m'
  cat <<'EOF'

 __          ________ _      _____ ____  __  __ ______
 \ \        / /  ____| |    / ____/ __ \|  \/  |  ____|
  \ \  /\  / /| |__  | |   | |   | |  | | \  / | |__
   \ \/  \/ / |  __| | |   | |   | |  | | |\/| |  __|
    \  /\  /  | |____| |___| |___| |__| | |  | | |____
     \/  \/   |______|______\_____\____/|_|  |_|______|

 _    _ __     __ ___
| |  | |\ \   / /|__ \
| |__| | \ \_/ /    ) |
|  __  |  \   /    / /
| |  | |   | |    / /_
|_|  |_|   |_|   |____|

EOF
  printf '\033[0m'
  echo "Welcome HY2"
  echo "作者 @keiraee"
  echo "开源地址：https://github.com/keiraee/hy2-allin-one.git"
  echo
}

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
  if [ -f "${XRAY_CONFIG:-}" ]; then
    chown hy2-aio:hy2-aio "$XRAY_CONFIG" 2>/dev/null || true
    chmod 0640 "$XRAY_CONFIG" 2>/dev/null || true
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

resolve_xray_port() {
  local hy2="${1:-${HY2_PORT:-8443}}"
  local panel="${2:-${PANEL_PORT:-443}}"
  local xray="${3:-${XRAY_PORT:-}}"
  if [ -n "$xray" ]; then
    printf '%s' "$xray"
    return 0
  fi
  if [ "$hy2" != "$panel" ]; then
    printf '%s' "$hy2"
    return 0
  fi
  if [ "$panel" != "8443" ]; then
    printf '%s' "8443"
    return 0
  fi
  printf '%s' "443"
}

validate_xray_port_layout() {
  local xray_port="${1:-}" panel_port="${2:-}" stats_port="${3:-}"
  port_number_is_valid "$xray_port" \
    || die "VLESS TCP 端口 ${xray_port:-<empty>} 无效；必须是 1-65535 的整数"
  [ "$xray_port" != "$panel_port" ] \
    || die "端口冲突：VLESS TCP 不能与面板端口同为 $xray_port"
  [ "$xray_port" != "$stats_port" ] \
    || die "端口冲突：VLESS TCP 不能与统计端口同为 $xray_port"
  [ "$xray_port" != "$BACKEND_PORT" ] \
    || die "端口冲突：VLESS TCP 不能使用内部后端端口 $BACKEND_PORT"
}

append_env_kv() {
  local key="$1" value="$2"
  [ -f "$ENV_FILE" ] || return 0
  grep -q "^${key}=" "$ENV_FILE" 2>/dev/null && return 0
  printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
}

ensure_reality_env() {
  REALITY_DEST="${REALITY_DEST:-$REALITY_DEST_DEFAULT}"
  if [ -z "${REALITY_SERVER_NAMES:-}" ]; then
    REALITY_SERVER_NAMES="${REALITY_DEST%%:*}"
  fi
  XRAY_PORT="${XRAY_PORT:-$(resolve_xray_port)}"
  REALITY_SHORT_ID="${REALITY_SHORT_ID:-$(openssl rand -hex 4)}"
  if [ -z "${REALITY_PRIVATE_KEY:-}" ] || [ -z "${REALITY_PUBLIC_KEY:-}" ]; then
    local xray_bin out priv pub
    if command -v xray >/dev/null 2>&1; then
      xray_bin="$(command -v xray)"
    elif [ -x "${XRAY_BIN:-/usr/local/bin/xray}" ]; then
      xray_bin="${XRAY_BIN:-/usr/local/bin/xray}"
    else
      die "需要 Xray 以生成 Reality 密钥"
    fi
    out="$("$xray_bin" x25519)" || die "xray x25519 失败"
    priv="$(printf '%s\n' "$out" | awk -F': ' '/^PrivateKey/{print $2; exit}' | tr -d '[:space:]')"
    # 兼容不同 Xray 版本：旧版输出 "Password"，新版输出 "PublicKey"
    pub="$(printf '%s\n' "$out" | awk -F': ' '/^(Password|PublicKey)/{print $2; exit}' | tr -d '[:space:]')"
    [ -n "$priv" ] && [ -n "$pub" ] || die "解析 Reality 密钥失败"
    REALITY_PRIVATE_KEY="$priv"
    REALITY_PUBLIC_KEY="$pub"
  fi
  if [ -f "$ENV_FILE" ]; then
    append_env_kv XRAY_PORT "$XRAY_PORT"
    append_env_kv REALITY_DEST "$REALITY_DEST"
    append_env_kv REALITY_SERVER_NAMES "$REALITY_SERVER_NAMES"
    append_env_kv REALITY_SHORT_ID "$REALITY_SHORT_ID"
    append_env_kv REALITY_PRIVATE_KEY "$REALITY_PRIVATE_KEY"
    append_env_kv REALITY_PUBLIC_KEY "$REALITY_PUBLIC_KEY"
    chown root:hy2-aio "$ENV_FILE" 2>/dev/null || true
    chmod 0640 "$ENV_FILE" 2>/dev/null || true
  fi
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
  XRAY_PORT="$(resolve_xray_port)"
  validate_xray_port_layout "$XRAY_PORT" "$PANEL_PORT" "$STATS_PORT"
  REALITY_DEST="${REALITY_DEST:-$REALITY_DEST_DEFAULT}"
  REALITY_SERVER_NAMES="${REALITY_SERVER_NAMES:-${REALITY_DEST%%:*}}"
  OBFS_ENABLED="${OBFS_ENABLED:-true}"
  QUIC_KEEP_ALIVE_PERIOD="${QUIC_KEEP_ALIVE_PERIOD:-5s}"
  QUIC_MAX_IDLE_TIMEOUT="${QUIC_MAX_IDLE_TIMEOUT:-120s}"
}

api_post() {
  : "${API_SECRET:?API_SECRET 未设置，请先 read_env}"
  curl -fsS --connect-timeout 5 --max-time 60 \
    -H "X-API-Secret: ${API_SECRET}" \
    -H "Content-Type: application/json" \
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

tcp_listen_pids() {
  local port="$1"
  ss -Hlntp 2>/dev/null | awk -v p=":$port" '
    ($4 ~ p"$" || $4 ~ p" ") {
      while (match($0, /pid=[0-9]+/)) {
        print substr($0, RSTART+4, RLENGTH-4)
        $0 = substr($0, RSTART+RLENGTH)
      }
    }' | sort -u
}

pid_cgroup() {
  cat "/proc/$1/cgroup" 2>/dev/null || true
}

# systemctl show 把数字参数当 job ID，不能用来查 PID 归属；从 cgroup 路径取服务名。
pid_service_name() {
  pid_cgroup "$1" | awk -F: '{n = split($NF, a, "/"); if (a[n] ~ /\.service$/) {print a[n]; exit}}'
}

disable_official_xray_units() {
  command -v systemctl >/dev/null 2>&1 || return 0
  local unit
  while read -r unit; do
    [ -n "$unit" ] || continue
    case "$unit" in
      xray.service|xray@*.service) ;;
      *) continue ;;
    esac
    log "停用官方 ${unit}，避免与 HY2 VLESS 抢 TCP 端口"
    systemctl disable --now "$unit" >/dev/null 2>&1 || systemctl stop "$unit" >/dev/null 2>&1 || true
  done < <(
    {
      systemctl list-unit-files --type=service --no-legend --no-pager 2>/dev/null || true
      systemctl list-units --all --type=service --plain --no-legend --no-pager 'xray*' 2>/dev/null || true
    } | awk '{print $1}'
  )
}

reclaim_vless_tcp_port() {
  local port="${1:-${XRAY_PORT:-}}" pid unit comm args
  [ -n "$port" ] || port="$(resolve_xray_port)"
  disable_official_xray_units
  for pid in $(tcp_listen_pids "$port"); do
    [ -n "$pid" ] || continue
    unit="$(pid_service_name "$pid")"
    [ "$unit" = "hy2-xray.service" ] && continue
    comm="$(ps -o comm= -p "$pid" 2>/dev/null | awk '{print $1}')" || true
    args="$(ps -ww -o args= -p "$pid" 2>/dev/null || true)"
    [ -n "$comm" ] || continue # ss 快照后进程已消失，端口已释放
    if [ "$comm" = "xray" ] && printf '%s' "$args" | grep -q '/usr/local/etc/xray/config.json'; then
      log "结束残留官方 Xray PID ${pid}"
      if [ -n "$unit" ] && [ "$unit" != "hy2-xray.service" ]; then
        systemctl stop "$unit" >/dev/null 2>&1 || true
      fi
      kill "$pid" 2>/dev/null || true
      sleep 1
      continue
    fi
    ss -Hlntp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" || $4 ~ p" "' >&2 || true
    die "VLESS TCP 端口 $port 已被占用（PID ${pid} ${comm:-?}）"
  done
}

restart_hy2_xray_or_die() {
  reclaim_vless_tcp_port "${XRAY_PORT:-}"
  systemctl restart hy2-xray.service || true
  sleep 1
  if ! systemctl is-active --quiet hy2-xray.service; then
    journalctl -u hy2-xray.service --no-pager -n 80 >&2 || true
    die "Xray 启动失败"
  fi
}

ensure_install_ports_available() {
  local hy2_port="$1" panel_port="$2" stats_port="$3" xray_port="${4:-}"
  validate_port_layout "$panel_port" "$stats_port"
  xray_port="$(resolve_xray_port "$hy2_port" "$panel_port" "$xray_port")"
  validate_xray_port_layout "$xray_port" "$panel_port" "$stats_port"
  port_is_used "$hy2_port" \
    && die "代理 UDP 端口 $hy2_port 已被占用"
  tcp_port_is_used "$panel_port" \
    && die "面板 TCP 端口 $panel_port 已被占用"
  tcp_port_is_used "$stats_port" \
    && die "统计 TCP 端口 $stats_port 已被占用"
  tcp_port_is_used "$BACKEND_PORT" \
    && die "内部后端 TCP 端口 $BACKEND_PORT 已被占用"
  if tcp_port_is_used "$xray_port"; then
    reclaim_vless_tcp_port "$xray_port"
  fi
  tcp_port_is_used "$xray_port" \
    && die "VLESS TCP 端口 $xray_port 已被占用"
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

# 套餐流量字节数：0 = 无限流量
validate_total_bytes() {
  local value="${1:-}"
  [[ "$value" =~ ^0$|^[1-9][0-9]*$ ]] \
    || die "套餐流量字节数无效：${value:-<empty>}（0 = 无限流量）"
}

# 流量单位换算：mb/gb/tb + 数值 → 字节（十进制 1000 进制）
traffic_plan_to_bytes() {
  python3 - "$1" "$2" <<'PY'
from decimal import Decimal
import sys

factors = {"mb": 1_000_000, "gb": 1_000_000_000, "tb": 1_000_000_000_000}
unit = sys.argv[1]
try:
    value = Decimal(sys.argv[2])
    assert value > 0
    factor = factors[unit]
except Exception:
    raise SystemExit(1)
print(int(value * factor))
PY
}

# 安装向导流量单位菜单映射：1=MB 2=GB 3=TB（默认） 4=无限流量
traffic_unit_from_choice() {
  case "${1:-}" in
    1) printf '%s' "mb" ;;
    2) printf '%s' "gb" ;;
    4) printf '%s' "unlimited" ;;
    ""|3) printf '%s' "tb" ;;
    *) return 1 ;;
  esac
}

# 解析套餐流量：设置 TOTAL_BYTES（0=无限）与 TRAFFIC_PLAN_LABEL，不产生 stdout。
# 优先级：HY2_TOTAL_BYTES > HY2_TOTAL_UNIT(+HY2_TOTAL_VALUE) > HY2_TOTAL_TB > 交互向导。
prompt_traffic_plan() {
  local unit value bytes factor_label choice
  TRAFFIC_PLAN_LABEL=""
  if [ -n "${HY2_TOTAL_BYTES:-}" ]; then
    validate_total_bytes "$HY2_TOTAL_BYTES"
    TOTAL_BYTES="$HY2_TOTAL_BYTES"
    if [ "$TOTAL_BYTES" = "0" ]; then
      TRAFFIC_PLAN_LABEL="无限流量"
    else
      TRAFFIC_PLAN_LABEL="${TOTAL_BYTES} 字节"
    fi
    return 0
  fi
  unit="$(printf '%s' "${HY2_TOTAL_UNIT:-}" | tr '[:upper:]' '[:lower:]')"
  value="${HY2_TOTAL_VALUE:-}"
  if [ -z "$unit" ] && [ -n "${HY2_TOTAL_TB:-}" ]; then
    unit="tb"
    value="$HY2_TOTAL_TB"
  fi
  case "$unit" in
    unlimited|none|inf|infinite|u)
      TOTAL_BYTES=0
      TRAFFIC_PLAN_LABEL="无限流量"
      return 0
      ;;
    mb|gb|tb) ;;
    "")
      if [ "${HY2_NONINTERACTIVE:-0}" = "1" ] || [ ! -t 0 ]; then
        unit="tb"
      else
        echo "  流量单位：1) MB   2) GB   3) TB   4) 无限流量" >&2
        read -r -p "选择流量单位 [1-4]（回车=3）: " choice || choice="3"
        unit="$(traffic_unit_from_choice "$choice")" || {
          warn "无效输入，已默认 TB"
          unit="tb"
        }
        if [ "$unit" = "unlimited" ]; then
          TOTAL_BYTES=0
          TRAFFIC_PLAN_LABEL="无限流量"
          return 0
        fi
      fi
      ;;
    *)
      die "HY2_TOTAL_UNIT 须为 mb/gb/tb/unlimited"
      ;;
  esac
  if [ -z "$value" ]; then
    case "$unit" in
      mb) factor_label="MB" ;;
      gb) factor_label="GB" ;;
      *) factor_label="TB" ;;
    esac
    value="$(prompt_value "套餐流量（${factor_label}）" '1')"
  fi
  bytes="$(traffic_plan_to_bytes "$unit" "$value")" || {
    warn "套餐流量格式错误：${value}"
    return 1
  }
  TOTAL_BYTES="$bytes"
  case "$unit" in
    mb) factor_label="MB" ;;
    gb) factor_label="GB" ;;
    *) factor_label="TB" ;;
  esac
  TRAFFIC_PLAN_LABEL="${value} ${factor_label}"
  return 0
}
