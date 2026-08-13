#!/usr/bin/env bash
# HY2 AIO - 一键部署 Hysteria 2 + 多用户订阅 + 轻量面板
# 用法：sudo bash hy2.sh install
#       sudo hy2

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Pin remote installs to a release tag by default (override with HY2_REPO_REF=main for tip).
DEFAULT_REPO_SLUG="keiraee/hy2-allin-one"
REPO_SLUG="${HY2_REPO:-$DEFAULT_REPO_SLUG}"
REPO_REF="${HY2_REPO_REF:-v1.3.23}"

apply_repo_url() {
  if [ -n "${HY2_REPO_URL:-}" ]; then
    REPO_URL="${HY2_REPO_URL%/}"
  else
    REPO_URL="https://raw.githubusercontent.com/${REPO_SLUG}/${REPO_REF}"
  fi
}

log_repo_source() {
  local label="${1:-来源}"
  _bootstrap_log "${label}：${REPO_SLUG} @ ${REPO_REF}"
  _bootstrap_log "模块地址：${REPO_URL}"
}

normalize_aio_version() {
  local v="${1:-}"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  [ -n "$v" ] || { printf '%s' "未知"; return 0; }
  case "$v" in
    v*) printf '%s' "$v" ;;
    [0-9]*) printf 'v%s' "$v" ;;
    *) printf '%s' "$v" ;;
  esac
}

read_installed_aio_version() {
  local env_file="${1:-/etc/hy2-aio/config.env}" value=""
  if [ -f "$env_file" ]; then
    value="$(awk -F= '/^AIO_VERSION=/{gsub(/\r/,""); print $2; exit}' "$env_file" || true)"
  fi
  normalize_aio_version "$value"
}

log_upgrade_plan() {
  local from to env_file="${1:-/etc/hy2-aio/config.env}"
  [ "${HY2_UPGRADE_BANNER:-0}" = "1" ] && return 0
  from="$(read_installed_aio_version "$env_file")"
  to="$(normalize_aio_version "${REPO_REF:-}")"
  _bootstrap_log "升级 ${from} → ${to}"
  HY2_UPGRADE_BANNER=1
  export HY2_UPGRADE_BANNER
}

apply_repo_url

# 临时函数（模块加载前使用）
_bootstrap_log() { printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
_bootstrap_die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# 下载远程模块（先拉 SHA256SUMS，再逐文件校验）
fetch_modules() {
  local target_dir="$1"
  mkdir -p "$target_dir/lib" "$target_dir/bin"
  local files=(
    "lib/core.sh"
    "lib/install.sh"
    "lib/config.sh"
    "lib/panel.sh"
    "lib/user.sh"
    "lib/cert.sh"
    "lib/access.sh"
    "lib/backup.sh"
    "lib/mode.sh"
    "lib/backend.sh"
    "lib/cli.sh"
    "bin/hy2.sh"
  )
  local sums tmp f expected
  sums="$(mktemp)"
  _bootstrap_log "下载：SHA256SUMS"
  curl -fsSL "${REPO_URL}/SHA256SUMS" -o "$sums" || { rm -f "$sums"; _bootstrap_die "下载 SHA256SUMS 失败（请确认已发布 ${REPO_REF}）"; }

  for f in "${files[@]}"; do
    _bootstrap_log "下载：$f"
    tmp="$(mktemp)"
    curl -fsSL "${REPO_URL}/${f}" -o "$tmp" || { rm -f "$tmp" "$sums"; _bootstrap_die "下载失败：$f"; }
    head -1 "$tmp" | grep -qE '^#!|^#' || { rm -f "$tmp" "$sums"; _bootstrap_die "模块内容校验失败：$f"; }
    [ -s "$tmp" ] || { rm -f "$tmp" "$sums"; _bootstrap_die "模块为空：$f"; }
    expected="$(awk -v name="$f" '{ gsub(/\r/, ""); if ($2 == name) { print $1; exit } }' "$sums")"
    [ -n "$expected" ] || { rm -f "$tmp" "$sums"; _bootstrap_die "SHA256SUMS 中缺少：$f"; }
    python3 - "$tmp" "$expected" <<'PY' || { rm -f "$tmp" "$sums"; _bootstrap_die "SHA256 校验失败：$f"; }
import hashlib, pathlib, sys
path = pathlib.Path(sys.argv[1])
expected = sys.argv[2].lower()
digest = hashlib.sha256(path.read_bytes()).hexdigest()
if digest != expected:
    raise SystemExit(f"got {digest}, want {expected}")
PY
    mv "$tmp" "${target_dir}/${f}"
  done
  rm -f "$sums"
}

# 加载本地模块（开发模式）
load_local_modules() {
  source "${SCRIPT_DIR}/lib/core.sh"
  source "${SCRIPT_DIR}/lib/install.sh"
  source "${SCRIPT_DIR}/lib/config.sh"
  source "${SCRIPT_DIR}/lib/panel.sh"
  source "${SCRIPT_DIR}/lib/user.sh"
  source "${SCRIPT_DIR}/lib/cert.sh"
  source "${SCRIPT_DIR}/lib/access.sh"
  source "${SCRIPT_DIR}/lib/backup.sh"
  source "${SCRIPT_DIR}/lib/mode.sh"
  source "${SCRIPT_DIR}/lib/backend.sh"
  source "${SCRIPT_DIR}/lib/cli.sh"
}

# 加载已安装的模块
load_installed_modules() {
  local modules_dir="/usr/local/lib/hy2-aio/modules"
  if [ -d "$modules_dir/lib" ]; then
    SCRIPT_DIR="$modules_dir"
    source "${modules_dir}/lib/core.sh"
    source "${modules_dir}/lib/install.sh"
    source "${modules_dir}/lib/config.sh"
    source "${modules_dir}/lib/panel.sh"
    source "${modules_dir}/lib/user.sh"
    source "${modules_dir}/lib/cert.sh"
    source "${modules_dir}/lib/access.sh"
    source "${modules_dir}/lib/backup.sh"
    source "${modules_dir}/lib/mode.sh"
    source "${modules_dir}/lib/backend.sh"
    source "${modules_dir}/lib/cli.sh"
  else
    die "模块未安装，请运行：sudo bash hy2.sh install"
  fi
}

resolve_latest_repo_ref() {
  local tag payload
  REPO_SLUG="${HY2_REPO:-$DEFAULT_REPO_SLUG}"
  payload="$(curl -fsSL "https://api.github.com/repos/${REPO_SLUG}/releases/latest")" \
    || _bootstrap_die "无法获取 GitHub latest release（${REPO_SLUG}）"
  tag="$(printf '%s' "$payload" | python3 -c 'import sys, json; print(json.load(sys.stdin)["tag_name"])')" \
    || _bootstrap_die "无法解析 latest release"
  [ -n "$tag" ] || _bootstrap_die "latest release 为空"
  REPO_REF="$tag"
  apply_repo_url
}

resolve_upgrade_source() {
  REPO_SLUG="${HY2_REPO:-$DEFAULT_REPO_SLUG}"
  if [ -z "${HY2_REPO_REF:-}" ] || [ "${HY2_REPO_REF}" = "latest" ]; then
    resolve_latest_repo_ref
  else
    REPO_REF="$HY2_REPO_REF"
    apply_repo_url
  fi
  log_upgrade_plan
  log_repo_source "模块来源"
}

# upgrade always fetches remote modules. Other commands use a checkout's lib/ when present.
choose_module_source() {
  local command="${1:-menu}"
  if [ "$command" = "upgrade" ]; then
    printf '%s\n' remote
    return
  fi
  if [ -f "${SCRIPT_DIR}/lib/core.sh" ]; then
    printf '%s\n' local
    return
  fi
  case "$command" in
    install|repair|help|-h|--help)
      printf '%s\n' remote
      ;;
    *)
      printf '%s\n' installed
      ;;
  esac
}

# 安装主流程
install_stack() {
  need_root install
  have_systemd || die "此脚本需要 systemd"
  [ -f /etc/os-release ] || die "无法识别系统"
  # shellcheck disable=SC1091
  source /etc/os-release
  detect_platform

  if [ -f "$ENV_FILE" ] && [ "${HY2_FORCE:-0}" != "1" ]; then
    die "HY2 AIO 已安装。查看状态：hy2 status"
  fi

  install_packages_v12

  echo
  echo "============================================================"
  echo " HY2 AIO 安装向导"
  echo " 一路回车 = 使用推荐默认值；要改再输入"
  echo "============================================================"
  echo

  local detected_ip=""
  detected_ip="${HY2_PUBLIC_IP:-$(detect_public_ipv4 || true)}"
  if [ -n "${HY2_PUBLIC_IP:-}" ]; then
    PUBLIC_IP="$HY2_PUBLIC_IP"
    echo "[1/6] 公网 IP：${PUBLIC_IP}（已由环境变量指定）"
  elif [ -n "$detected_ip" ]; then
    echo "[1/6] 公网 IP"
    PUBLIC_IP="$(prompt_value '确认公网 IP（不对再改）' "$detected_ip")"
  else
    echo "[1/6] 公网 IP"
    PUBLIC_IP=""
    if [ -t 0 ] && [ "${HY2_NONINTERACTIVE:-0}" != "1" ]; then
      while [ -z "$PUBLIC_IP" ]; do
        read -r -p "未能自动检测，请输入公网 IPv4: " PUBLIC_IP || true
      done
    fi
  fi
  [ -n "$PUBLIC_IP" ] || die "必须提供公网 IPv4（可设 HY2_PUBLIC_IP=x.x.x.x）"

  echo
  echo "[2/6] 代理端口"
  HY2_PORT="${HY2_PORT:-$(prompt_hysteria_port)}"
  [[ "$HY2_PORT" =~ ^[0-9]+$ ]] && [ "$HY2_PORT" -ge 1 ] && [ "$HY2_PORT" -le 65535 ] \
    || die "代理端口无效（内部错误，请升级安装脚本）：${HY2_PORT}"

  echo
  echo "[3/6] 面板端口"
  PANEL_PORT="${HY2_PANEL_PORT:-$(prompt_panel_port)}"
  panel_port_is_valid "$PANEL_PORT" \
    || die "面板端口 ${PANEL_PORT} 无效或不安全；管理面板仅支持 HTTPS，禁止使用 80"
  STATS_PORT="${HY2_STATS_PORT:-$(prompt_stats_port)}"
  validate_port_layout "$PANEL_PORT" "$STATS_PORT"
  ensure_install_ports_available "$HY2_PORT" "$PANEL_PORT" "$STATS_PORT"

  NETWORK_INTERFACE="${HY2_INTERFACE:-$(detect_iface)}"
  [ -n "$NETWORK_INTERFACE" ] || die "无法检测默认网卡"

  local default_domain="${PUBLIC_IP//./-}.sslip.io"
  local users_count total_tb custom_domain confirm=""
  echo
  echo "[4/6] 账号数量"
  users_count="${HY2_USERS:-$(prompt_value '要创建几个用户' '5')}"
  [[ "$users_count" =~ ^[1-9][0-9]?$ ]] || die "用户数量必须是 1-99"

  echo
  echo "[5/6] 套餐流量"
  total_tb="${HY2_TOTAL_TB:-$(prompt_value '套餐总流量（TB）' '1')}"
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

  echo
  echo "[6/6] 域名与伪装"
  custom_domain="${HY2_DOMAIN:-$(prompt_value '面板/订阅域名（没有域名就回车）' "$default_domain")}"
  DOMAIN="${custom_domain:-$default_domain}"
  PANEL_USER="${HY2_PANEL_USER:-admin}"
  PANEL_PASS="${HY2_PANEL_PASS:-$(rand_hex 12)}"
  PANEL_PATH="${HY2_PANEL_PATH:-hy2-$(rand_hex 12)}"
  OBFS_PASSWORD="$(rand_hex 16)"
  echo
  OBFS_ENABLED="$(prompt_obfs_enabled)"
  case "$OBFS_ENABLED" in
    true|false) ;;
    *) die "混淆开关无效（内部错误，请升级安装脚本）：${OBFS_ENABLED}" ;;
  esac
  API_SECRET="$(rand_hex 24)"
  SNI="${HY2_SNI:-www.amazon.sg}"
  BACKUP_RETENTION_DAYS="${HY2_BACKUP_DAYS:-14}"
  RATE_LIMIT_SUBSCRIPTION="${HY2_RATE_LIMIT_SUBSCRIPTION:-30}"
  RATE_LIMIT_API="${HY2_RATE_LIMIT_API:-120}"
  SPEED_TEST="${HY2_SPEED_TEST:-false}"
  QUIC_KEEP_ALIVE_PERIOD="${HY2_QUIC_KEEP_ALIVE_PERIOD:-5s}"
  QUIC_MAX_IDLE_TIMEOUT="${HY2_QUIC_MAX_IDLE_TIMEOUT:-120s}"
  # IP / sslip 证书无法校验真实 SNI，默认 disable；真实域名可设 HY2_SNI_GUARD=strict
  if [ -n "${HY2_SNI_GUARD:-}" ]; then
    SNI_GUARD="$HY2_SNI_GUARD"
  elif [[ "$DOMAIN" == *sslip.io ]] || [[ "$DOMAIN" == "$PUBLIC_IP" ]]; then
    SNI_GUARD="disable"
  else
    SNI_GUARD="strict"
  fi
  if [ -n "${HY2_CLIENT_INSECURE:-}" ]; then
    CLIENT_INSECURE="$HY2_CLIENT_INSECURE"
  elif [[ "$DOMAIN" == *sslip.io ]] || [[ "$DOMAIN" == "$PUBLIC_IP" ]]; then
    CLIENT_INSECURE="true"
  else
    CLIENT_INSECURE="false"
  fi

  python3 - "$PUBLIC_IP" <<'PYV' || die "公网 IPv4 格式错误：$PUBLIC_IP"
import ipaddress, sys
value = ipaddress.ip_address(sys.argv[1])
assert value.version == 4
PYV
  [[ "$NETWORK_INTERFACE" =~ ^[A-Za-z0-9_.:-]+$ ]] || die "网卡名称格式错误"
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || die "域名格式错误"
  [[ "$PANEL_USER" =~ ^[A-Za-z0-9_-]{1,32}$ ]] || die "面板用户名格式错误"
  [[ "$PANEL_PATH" =~ ^[A-Za-z0-9_-]{4,80}$ ]] || die "面板路径格式错误"
  if [ "${#PANEL_PASS}" -lt 8 ] || [ "${#PANEL_PASS}" -gt 128 ]; then
    die "面板密码长度须为 8-128"
  fi
  case "$PANEL_PASS" in
    *$'\n'*|*$'\r'*|*=*) die "面板密码不能包含换行或等号" ;;
  esac
  [[ "$SNI" =~ ^[A-Za-z0-9.-]+$ ]] || die "SNI 格式错误"
  [[ "$TOTAL_BYTES" =~ ^[1-9][0-9]*$ ]] || die "TOTAL_BYTES 必须是正整数"
  [[ "$BACKUP_RETENTION_DAYS" =~ ^[1-9][0-9]{0,3}$ ]] \
    && [ "$BACKUP_RETENTION_DAYS" -le 3650 ] \
    || die "备份保留天数必须是 1-3650 的整数"
  [[ "$RATE_LIMIT_SUBSCRIPTION" =~ ^[0-9]+$ ]] || die "订阅限流必须是整数"
  [[ "$RATE_LIMIT_API" =~ ^[0-9]+$ ]] || die "面板 API 限流必须是整数"
  case "$SPEED_TEST" in
    true|false) ;;
    *) die "SPEED_TEST 只能是 true 或 false" ;;
  esac
  case "$BACKUP_RETENTION_DAYS$RATE_LIMIT_SUBSCRIPTION$RATE_LIMIT_API$SPEED_TEST" in
    *$'\n'*|*$'\r'*) die "配置值不能包含换行" ;;
  esac

  echo
  echo "------------------------------------------------------------"
  echo " 即将安装，请确认："
  echo "  公网 IP     : $PUBLIC_IP"
  echo "  网卡        : $NETWORK_INTERFACE"
  echo "  代理 UDP    : $HY2_PORT"
  echo "  面板 HTTPS  : $PANEL_PORT"
  echo "  域名        : $DOMAIN"
  echo "  用户数量    : $users_count"
  echo "  套餐流量    : $total_tb TB"
  echo "  流量伪装    : $OBFS_ENABLED"
  echo "------------------------------------------------------------"
  if [ -t 0 ] && [ "${HY2_NONINTERACTIVE:-0}" != "1" ]; then
    read -r -p "回车开始安装，输入 n 取消: " confirm || true
    confirm="$(printf '%s' "$confirm" | tr '[:upper:]' '[:lower:]')"
    case "$confirm" in
      n|no) die "已取消安装" ;;
    esac
  fi
  echo
  log "开始安装…"

  configure_swap_and_kernel
  install_hysteria
  install_caddy_v12

  getent group hysteria >/dev/null 2>&1 || groupadd --system hysteria
  id hysteria >/dev/null 2>&1 || useradd --system --gid hysteria --home /nonexistent --shell /usr/sbin/nologin hysteria
  ensure_hy2_aio_user

  install -d -o root -g hy2-aio -m 0770 "$CONFIG_DIR"
  install -d -o hy2-aio -g hy2-aio -m 0750 "$STATE_DIR" "$STATE_DIR/backups"
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
OBFS_ENABLED=$OBFS_ENABLED
API_SECRET=$API_SECRET
PANEL_PATH=$PANEL_PATH
PANEL_USER=$PANEL_USER
PANEL_PASS=$PANEL_PASS
SNI=$SNI
BACKUP_RETENTION_DAYS=$BACKUP_RETENTION_DAYS
RATE_LIMIT_SUBSCRIPTION=$RATE_LIMIT_SUBSCRIPTION
RATE_LIMIT_API=$RATE_LIMIT_API
SPEED_TEST=$SPEED_TEST
QUIC_KEEP_ALIVE_PERIOD=$QUIC_KEEP_ALIVE_PERIOD
QUIC_MAX_IDLE_TIMEOUT=$QUIC_MAX_IDLE_TIMEOUT
SNI_GUARD=$SNI_GUARD
CLIENT_INSECURE=$CLIENT_INSECURE
EOF
  chown root:hy2-aio "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  configure_firewall_v12

  generate_users "$users_count"
  ensure_mode_file
  create_certificate
  write_rebuild_helper
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG"
  chmod 0660 "$HYSTERIA_CONFIG"

  write_backend
  write_panel
  write_systemd
  write_caddy
  write_access_file
  ensure_hysteria_config_perms

  # 安装模块到系统目录
  local modules_dir="/usr/local/lib/hy2-aio/modules"
  [ -f "${SCRIPT_DIR}/lib/core.sh" ] || die "找不到模块源：${SCRIPT_DIR}/lib/core.sh"
  mkdir -p "$modules_dir/lib" "$modules_dir/bin"
  cp -a "${SCRIPT_DIR}/lib/"* "$modules_dir/lib/"
  cp -a "${SCRIPT_DIR}/bin/"* "$modules_dir/bin/"

  systemctl daemon-reload
  systemctl enable hysteria-server.service hy2-aio.service hy2-aio-reload-hysteria.path caddy.service >/dev/null
  systemctl restart hysteria-server.service
  sleep 2
  systemctl restart hy2-aio.service
  systemctl start hy2-aio-reload-hysteria.path
  systemctl restart caddy.service
  sleep 3
  wait_services

  api_post sync >/dev/null || true

  # 安装系统命令入口
  install_hy2_cli "${modules_dir}/bin/hy2.sh"

  write_access_file
  test_https

  local port_suffix=""
  [ "${PANEL_PORT:-443}" != "443" ] && port_suffix=":${PANEL_PORT}"

  echo
  echo "============================================================"
  echo " 安装完成"
  echo "============================================================"
  echo "面板地址：https://${DOMAIN}${port_suffix}/${PANEL_PATH}/"
  echo "面板账号：${PANEL_USER}"
  echo "面板密码：请查看 ${ACCESS_FILE}"
  echo "账号/订阅：hy2 show"
  echo "            或打开上面的面板复制订阅"
  echo
  echo "以后常用（需 root；有 sudo 可加 sudo）："
  echo "  hy2           # 菜单"
  echo "  hy2 show      # 看账号和订阅"
  echo "  hy2 obfs off  # 断线频繁时可关伪装"
  echo "  hy2 upgrade   # 升级 AIO 到最新版"
  echo
  echo "云控制台防火墙请放行：TCP 80、TCP ${PANEL_PORT}、UDP ${HY2_PORT}"
  echo "============================================================"
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
    warn "面板 HTTPS 暂未成功。请确认云控制台已放行 TCP 80、TCP ${PANEL_PORT}、UDP ${HY2_PORT}。"
    warn "Caddy 日志：journalctl -u caddy -n 100 --no-pager"
  else
    log "HTTPS 面板测试成功：HTTP 200"
  fi
}

auto_cmd() {
  need_root auto

  if [ ! -f "$SERVICE_FILE" ]; then
    install_stack
    return
  fi

  local problems=()
  [ -f "$ENV_FILE" ] || problems+=("缺少 $ENV_FILE")
  [ -f "$APP_FILE" ] || problems+=("缺少 $APP_FILE")
  systemctl is-active --quiet hy2-aio.service || problems+=("hy2-aio.service 未运行")

  if [ "${#problems[@]}" -eq 0 ]; then
    log "HY2 AIO 运行正常"
    return
  fi

  echo "检测到问题："
  printf '  - %s\n' "${problems[@]}"
  echo "0. 修复"
  echo "1. 跳过"
  [ -t 0 ] || { warn "请使用 ssh -t 选择修复"; return 1; }
  local choice
  read -r -p "请选择 [0/1]: " choice || choice="1"
  [ "$choice" = "0" ] && repair_cmd || log "跳过修复"
}

usage() {
  cat <<EOF
HY2 AIO v${AIO_VERSION}

用法：
  bash hy2.sh install          # 安装（需 root）
  bash hy2.sh repair           # 按本脚本钉死的版本拉取并修复
  bash hy2.sh upgrade          # 拉 GitHub 最新版并修复
  hy2                          # 打开交互菜单
  hy2 upgrade                  # 同上（装好后推荐）

说明：管理命令需要 root。已是 root 直接 hy2；有 sudo 可写 sudo hy2。

菜单模式：
  hy2                          # 打开菜单

命令模式：
  hy2 status                   # 查看状态
  hy2 show                     # 显示账号
  hy2 sync                     # 同步数据
  hy2 mode                     # 速率模式菜单
  hy2 mode show                # 显示当前模式
  hy2 users                    # 用户列表
  hy2 add-user <用户名>        # 添加用户
  hy2 remove-user <用户名>     # 删除用户
  hy2 rotate-user <用户名>     # 轮换密钥
  hy2 note <用户名> [备注]     # 设置设备备注（留空清除）
  hy2 disable <用户名>         # 禁用用户
  hy2 enable <用户名>          # 启用用户
  hy2 on                       # 开启 Hysteria（需至少一个已启用用户）
  hy2 off                      # 关闭 Hysteria（停监听，不删用户）
  hy2 backup                   # 备份
  hy2 rollback                 # 回滚最近快照
  hy2 logs [行数]              # 查看日志
  hy2 restart                  # 重启 Hysteria + 面板后端 + Caddy
  hy2 update                   # 更新 Hysteria
  hy2 upgrade                  # 升级 HY2 AIO 到最新 Release
  hy2 repair                   # 用当前已装模块修复
  hy2 uninstall                # 卸载（保留配置；彻底删除用 HY2_PURGE=1）
  hy2 obfs show                # 查看混淆状态
  hy2 obfs on|off              # 开启/关闭 Salamander 混淆
  hy2 help|-h|--help|-help

无人值守安装：
  sudo HY2_NONINTERACTIVE=1 HY2_USERS=5 HY2_TOTAL_TB=1 bash hy2.sh install

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
  HY2_PORT            Hysteria UDP 端口，安装向导默认 8443
  HY2_OBFS            Salamander 混淆 0/1，默认 1（开）
  HY2_SPEED_TEST      开启 Hysteria speedTest（默认 false）
  HY2_SNI_GUARD       SNI 校验：disable|strict（真实域名默认 strict）
  HY2_CLIENT_INSECURE 客户端 skip-cert-verify（真实域名默认 false）
  HY2_BACKUP_DAYS     备份保留天数，默认 14
  HY2_RATE_LIMIT_SUBSCRIPTION  订阅 /s/ 每 IP 每分钟次数，默认 30
  HY2_RATE_LIMIT_API  面板 API 每 IP 每分钟次数，默认 120
  HY2_REPO            GitHub 仓库 slug，默认 keiraee/hy2-allin-one
  HY2_REPO_URL        模块下载地址（覆盖 raw 默认；fork 请优先用 HY2_REPO）
  HY2_REPO_REF        Git 分支/tag/commit，默认 v1.3.23；upgrade 空值=latest
  HY2_YES             设为 1 跳过卸载确认
  HY2_PURGE           设为 1 时卸载并删除配置/数据
  HYSTERIA_VERSION    钉死的 Hysteria 版本，默认 v2.12.1
  CADDY_VERSION       钉死的 Caddy 版本（非 apt 回退），默认 v2.11.4
EOF
}

# 主入口
main() {
  local command="${1:-menu}"
  local module_source tmp_dir

  # upgrade 始终按仓库参数链拉取；开发树的 lib/ 只用于 install/repair/日常命令。
  module_source="$(choose_module_source "$command")"
  case "$module_source" in
    remote)
      if [ "$command" = "upgrade" ]; then
        resolve_upgrade_source
      else
        apply_repo_url
        if [ "$command" = "repair" ]; then
          log_upgrade_plan
        fi
        log_repo_source "模块来源"
      fi
      tmp_dir="$(mktemp -d)"
      fetch_modules "$tmp_dir"
      SCRIPT_DIR="$tmp_dir"
      load_local_modules
      ;;
    local)
      load_local_modules
      ;;
    *)
      if [ -f "/usr/local/lib/hy2-aio/modules/lib/core.sh" ]; then
        load_installed_modules
      else
        _bootstrap_die "模块未安装。请运行：sudo bash hy2.sh install   或先 git clone 完整仓库再 repair"
      fi
      ;;
  esac

  # 解析命令
  case "$command" in
    menu)       menu_interactive ;;
    install)    install_stack ;;
    repair)     repair_cmd ;;
    upgrade)    repair_cmd ;;
    status)     status_cmd ;;
    show)       show_cmd ;;
    sync)       sync_cmd ;;
    mode)       mode_cmd "$@" ;;
    backup)     backup_cmd ;;
    rollback)   rollback_cmd ;;
    logs)       logs_cmd "${2:-}" ;;
    restart)    restart_cmd ;;
    users)      users_cmd ;;
    add-user)   modify_user "add-user" "${2:-}" ;;
    remove-user) modify_user "remove-user" "${2:-}" ;;
    rotate-user) modify_user "rotate-user" "${2:-}" ;;
    note)       modify_user "note" "${2:-}" "${3:-}" ;;
    disable)    modify_user "disable" "${2:-}" ;;
    enable)     modify_user "enable" "${2:-}" ;;
    on)         hy2_on_cmd ;;
    off)        hy2_off_cmd ;;
    update)     update_cmd ;;
    uninstall)  uninstall_cmd ;;
    obfs)       obfs_cmd "${2:-show}" ;;
    help|-h|--help|-help) usage ;;
    *)          usage; exit 1 ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
