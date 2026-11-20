#!/usr/bin/env bash
# core.sh - 基础工具函数

set -Eeuo pipefail

SCRIPT_VERSION="1.7.3"
AIO_VERSION="$SCRIPT_VERSION"
XRAY_VERSION="v26.3.27"
CONFIG_DIR="/etc/hy2-aio"
HYSTERIA_DIR="/etc/hysteria"
HYSTERIA_HOME_DIR="/var/lib/hysteria"
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

# 静默装一个包（成功返回 0）。依赖自检/端口跳跃都靠它补缺件，
# 避免每个调用点各写一遍 apt/dnf/yum/zypper 分支。
pkg_install_quiet() {
  [ -n "${1:-}" ] || return 1
  if [ -z "${PKG_MANAGER:-}" ]; then
    # detect_platform 会 die，装包场景不能让它把整个流程带走
    have_systemd || return 1
    if command -v apt-get >/dev/null 2>&1; then
      PKG_MANAGER="apt"
    elif command -v dnf >/dev/null 2>&1; then
      PKG_MANAGER="dnf"
    elif command -v yum >/dev/null 2>&1; then
      PKG_MANAGER="yum"
    elif command -v zypper >/dev/null 2>&1; then
      PKG_MANAGER="zypper"
    else
      return 1
    fi
    export PKG_MANAGER
  fi
  case "$PKG_MANAGER" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      # 缓存可能是空的（最小化镜像 / 刚从快照恢复），先 update 一次再装
      apt-get update >/dev/null 2>&1 || true
      apt-get install -y "$1" >/dev/null 2>&1
      ;;
    dnf|yum)
      "$PKG_MANAGER" install -y "$1" >/dev/null 2>&1
      ;;
    zypper)
      zypper --non-interactive install "$1" >/dev/null 2>&1
      ;;
    *)
      return 1
      ;;
  esac
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

port_hop_enabled() {
  local raw
  raw="$(printf '%s' "${PORT_HOP_ENABLED:-false}" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

# 默认范围：从代理端口起往后 1000 个，封顶 65535。
# 代理端口已经顶到 65535 时推不出「结束 > 开始」的范围，返回非零，
# 由调用方给出人话提示（否则会抛一句「结束端口必须大于开始端口」，
# 用户根本不知道这句话跟自己的 HY2_PORT 有关）。
default_hop_range() {
  local start="${HY2_PORT:-8443}" end
  port_number_is_valid "$start" || return 1
  end=$((10#$start + 1000))
  [ "$end" -le 65535 ] || end=65535
  [ "$((10#$end))" -gt "$((10#$start))" ] || return 1
  printf '%s-%s' "$start" "$end"
}

hop_range() {
  if [ -n "${PORT_HOP_RANGE:-}" ]; then
    printf '%s' "$PORT_HOP_RANGE"
  else
    default_hop_range
  fi
}

# Hysteria 只给基准端口以外的端口建重定向（基准端口自己监听），
# 所以 8443-9443 的规则实际是 8444-9443 → 8443。
# 只有一个待重定向端口时（如 8443-8444）Hysteria 的 nftPortExpr/
# iptablesPortExpr 只写单个数字，不写 "8444-8444"，这里跟着对齐，
# 否则自检 grep 永远匹配不上，把正常机器判成坏机器。
hop_redirect_range() {
  local range start end
  range="$(hop_range)" || return 1
  hop_range_is_valid "$range" || return 1
  start=$((10#${HY2_PORT:-443} + 1))
  end="${range##*-}"
  end=$((10#$end))
  [ "$start" -eq "$end" ] && { printf '%s' "$start"; return 0; }
  printf '%s-%s' "$start" "$end"
}

hop_range_is_valid() {
  local range="${1:-}" start end
  [[ "$range" =~ ^([0-9]{1,5})-([0-9]{1,5})$ ]] || return 1
  start="${BASH_REMATCH[1]}"
  end="${BASH_REMATCH[2]}"
  port_number_is_valid "$start" && port_number_is_valid "$end" || return 1
  [ $((10#$start)) -eq $((10#${HY2_PORT:-443})) ] || return 1
  [ $((10#$end)) -gt $((10#$start)) ] || return 1
  [ $((10#$end - 10#$start)) -le 2000 ] || return 1
}

validate_hop_range() {
  local range="${1:-}" start="" end=""
  [[ "$range" =~ ^([0-9]{1,5})-([0-9]{1,5})$ ]] \
    || die "端口跳跃范围格式应为 开始-结束（如 ${HY2_PORT:-8443}-$((10#${HY2_PORT:-8443} + 1000))）：${range:-<empty>}"
  start="${BASH_REMATCH[1]}"
  end="${BASH_REMATCH[2]}"
  port_number_is_valid "$start" && port_number_is_valid "$end" \
    || die "端口跳跃范围超出 1-65535：$range"
  [ $((10#$start)) -eq $((10#${HY2_PORT:-443})) ] \
    || die "端口跳跃范围必须从代理端口 ${HY2_PORT:-443} 开始：$range"
  [ $((10#$end)) -gt $((10#$start)) ] \
    || die "端口跳跃范围结束端口必须大于开始端口：$range"
  [ $((10#$end - 10#$start)) -le 2000 ] \
    || die "端口跳跃范围跨度过大（最多 2000 个额外端口）：$range"
  return 0
}

hop_interval_is_valid() {
  local value="${1:-}"
  [[ "$value" =~ ^[0-9]{1,4}$ ]] \
    && [ $((10#$value)) -ge 5 ] \
    && [ $((10#$value)) -le 3600 ]
}

validate_hop_interval() {
  local value="${1:-}"
  hop_interval_is_valid "$value" \
    || die "端口跳跃间隔须为 5-3600 的整数秒：${value:-<empty>}"
}

# 清理 Hysteria 遗留的 NAT 重定向规则。
#
# 背景：Hysteria 开 listen 端口范围时，自己建 iptables 链 HYSTERIA-PR-<hash>
# 或 nft 表 hysteria_<hash>，正常退出时会删掉。但它刚起来 1 秒就被 systemctl
# 杀掉（重启、部署时的典型情形）时，清理可能没跑完，链就留下来了。下次启动
# `iptables -N` 撞上同名链直接 FATAL：「Chain already exists」，服务永远起不来。
# （Hysteria 2.12.1 的已知脆弱点，2.14.0 才修。）
#
# 安全性：只按 HYSTERIA-PR- / hysteria_ 前缀精确匹配，绝不 `iptables -F`
# 全清，不碰任何其他规则、不碰 users.json / state.json / 流量统计。
# 调用时机必须是「Hysteria 已停止」之后，否则会短暂中断在线转发。
clean_hysteria_nat_rules() {
  # 全程不能依赖「命令成功」的返回码：脚本是 set -Eeuo pipefail，
  # 函数体内任何一条命令返回非零都会让整个函数当场退出，
  # 后面该清的链全被跳过（这正是第一次写完时清理没生效的原因）。
  local removed=0 refs r ipt fam tbl

  # --- iptables / ip6tables ---
  for ipt in iptables ip6tables; do
    command -v "$ipt" >/dev/null 2>&1 || continue

    # 1) 先摘掉主链里引用它们的规则，否则 -X 会报「Too many links」。
    #    注意：for 循环体内不要用管道，管道会在子 shell 里跑，removed 加不上。
    refs="$("$ipt" -t nat -S 2>/dev/null | sed -n 's/^-A \(.*-j HYSTERIA-PR-[^ ]*.*\)$/\1/p' || true)"
    if [ -n "$refs" ]; then
      while IFS= read -r r; do
        if [ -n "$r" ]; then
          # shellcheck disable=SC2086
          "$ipt" -t nat -D $r >/dev/null 2>&1 || true
        fi
      done <<EOF
$refs
EOF
    fi

    # 2) 再逐个清空并删除自建链
    while IFS= read -r r; do
      if [ -n "$r" ]; then
        "$ipt" -t nat -F "$r" >/dev/null 2>&1 || true
        if "$ipt" -t nat -X "$r" >/dev/null 2>&1; then
          removed=$((removed + 1))
        fi
      fi
    done <<EOF
$("$ipt" -t nat -S 2>/dev/null | sed -n 's/^-N \(HYSTERIA-PR-[^ ]*\)$/\1/p' || true)
EOF
  done

  # --- nftables ---
  if command -v nft >/dev/null 2>&1; then
    while read -r fam tbl; do
      if [ -n "$fam" ] && [ -n "$tbl" ]; then
        if nft delete table "$fam" "$tbl" >/dev/null 2>&1; then
          removed=$((removed + 1))
        fi
      fi
    done <<EOF
$(nft list tables 2>/dev/null | awk '/^table /{print $2, $3}' | grep -E 'hysteria_[^ ]+$' || true)
EOF
  fi

  # 用显式 if 而不是 [ ... ] 结尾：后者在 removed=0 时返回 1，
  # 配合 set -e 会让调用方误当成命令失败。
  if [ "$removed" -gt 0 ]; then
    return 0
  fi
  return 1
}

# 检测是否有残留（不修改任何东西），给自检用。
hysteria_nat_leftovers() {
  {
    if command -v iptables >/dev/null 2>&1; then
      iptables -t nat -S 2>/dev/null | sed -n 's/^-N \(HYSTERIA-PR-[^ ]*\)$/iptables \1/p'
    fi
    if command -v ip6tables >/dev/null 2>&1; then
      ip6tables -t nat -S 2>/dev/null | sed -n 's/^-N \(HYSTERIA-PR-[^ ]*\)$/ip6tables \1/p'
    fi
    if command -v nft >/dev/null 2>&1; then
      nft list tables 2>/dev/null | awk '/^table /{print $2, $3}' | grep -E 'hysteria_[^ ]+$' || true
    fi
  } | awk 'NF'
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
  PORT_HOP_ENABLED="${PORT_HOP_ENABLED:-false}"
  if port_hop_enabled; then
    PORT_HOP_RANGE="${PORT_HOP_RANGE:-$(default_hop_range)}"
    PORT_HOP_INTERVAL="${PORT_HOP_INTERVAL:-30}"
    # 这里只警告不退出：range 写坏时仍要允许 `hy2 hop off` 把功能关掉恢复。
    hop_range_is_valid "$PORT_HOP_RANGE" \
      || warn "PORT_HOP_RANGE 无效：${PORT_HOP_RANGE}（须从 ${HY2_PORT:-443} 开始、跨度 ≤2000）"
    hop_interval_is_valid "$PORT_HOP_INTERVAL" \
      || warn "PORT_HOP_INTERVAL 无效：${PORT_HOP_INTERVAL}（须为 5-3600 的整数秒）"
  fi
}

api_post() {
  : "${API_SECRET:?API_SECRET 未设置，请先 read_env}"
  curl -fsS --connect-timeout 5 --max-time 60 \
    -H "X-API-Secret: ${API_SECRET}" \
    -H "Content-Type: application/json" \
    -X POST "http://${BACKEND_HOST}:${BACKEND_PORT}/$1"
}

# 把用户踢下线（Hysteria POST /kick）。
#
# Hysteria 的 userpass 认证只在**建立连接时**校验，所以光把 users.json 里的
# disabled 置 true 是不够的 —— 已经挂着的人不断线就能一直用。这个函数负责
# 主动断开他的现有连接。日志里记录 disconnected 后会立刻断。
#
# 失败不算错误：Hysteria 没在跑 / 统计端口没开 / secret 不对，都只是没踢成，
# 不该让 disable 这类操作失败。调用方用 `|| true` 兜。
kick_hysteria_user() {
  local username="${1:-}" port="${STATS_PORT:-9999}" secret="${API_SECRET:-}"
  [ -n "$username" ] || return 1
  [ -n "$secret" ] || return 1
  [ -f "${HY2_OFF_FILE:-/etc/hy2-aio/hy2.off}" ] && return 1

  # body 是 JSON 字符串数组：["name"]
  local body
  body="$(printf '%s' "$username" | python3 -c 'import json,sys; print(json.dumps([sys.stdin.read().strip()]))' 2>/dev/null)" || return 1
  [ -n "$body" ] || return 1

  curl -fsS --connect-timeout 3 --max-time 8 \
    -H "Authorization: ${secret}" \
    -H "Content-Type: application/json" \
    -X POST --data "$body" \
    "http://127.0.0.1:${port}/kick" >/dev/null 2>&1 || return 1
  log "已断开 ${username} 的现有连接"
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
