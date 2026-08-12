#!/usr/bin/env bash
# HY2 AIO - 一键部署 Hysteria 2 + 多用户订阅 + 轻量面板
# 用法：sudo bash hy2.sh install
#       sudo hy2

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_REF="${HY2_REPO_REF:-main}"
if [ -n "${HY2_REPO_URL:-}" ]; then
  REPO_URL="$HY2_REPO_URL"
else
  REPO_URL="https://raw.githubusercontent.com/keiraee/hy2-allin-one/${REPO_REF}"
fi

# 临时函数（模块加载前使用）
_bootstrap_log() { printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
_bootstrap_die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# 下载远程模块
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
    "bin/hy2.sh"
  )
  local f tmp
  for f in "${files[@]}"; do
    _bootstrap_log "下载：$f"
    tmp="$(mktemp)"
    curl -fsSL "${REPO_URL}/${f}" -o "$tmp" || { rm -f "$tmp"; _bootstrap_die "下载失败：$f"; }
    head -1 "$tmp" | grep -qE '^#!|^#' || { rm -f "$tmp"; _bootstrap_die "模块内容校验失败：$f"; }
    [ -s "$tmp" ] || { rm -f "$tmp"; _bootstrap_die "模块为空：$f"; }
    mv "$tmp" "${target_dir}/${f}"
  done
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
}

# 加载已安装的模块
load_installed_modules() {
  local modules_dir="/usr/local/lib/hy2-aio/modules"
  if [ -d "$modules_dir/lib" ]; then
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
  else
    die "模块未安装，请运行：sudo bash hy2.sh install"
  fi
}

# 主菜单
show_menu() {
  clear
  cat <<'EOF'
 _   _ ____   __     _____ ___
| | | |___ \  \ \   / /_ _|_ _|
| |_| | __) |  \ \ / / | | | |
|  _  |/ __/    \ V /  | | | |
|_| |_|_____|    \_/  |___|___|

HY2 AIO - 一键部署 Hysteria 2

EOF
  echo "  0) 状态"
  echo "  1) 安装"
  echo "  2) 显示账号"
  echo "  3) 添加用户"
  echo "  4) 删除用户"
  echo "  5) 轮换用户密钥"
  echo "  6) 速率模式"
  echo "  7) 同步数据"
  echo "  8) 备份"
  echo "  9) 日志"
  echo " 10) 重启服务"
  echo " 11) 更新 Hysteria"
  echo " 12) 卸载"
  echo " 13) 设置用户备注"
  echo " 14) 禁用/启用用户"
  echo "  99) 退出"
  echo
}

# 菜单交互
menu_interactive() {
  while true; do
    show_menu
    read -r -p "请选择 [0-14/99]: " choice
    case "$choice" in
      0)  status_cmd ;;
      1)  install_stack ;;
      2)  show_cmd ;;
      3)
        read -r -p "请输入用户名：" username
        modify_user "add-user" "$username"
        ;;
      4)
        read -r -p "请输入用户名：" username
        modify_user "remove-user" "$username"
        ;;
      5)
        read -r -p "请输入用户名：" username
        modify_user "rotate-user" "$username"
        ;;
      6)  mode_interactive ;;
      7)  sync_cmd ;;
      8)  backup_cmd ;;
      9)  logs_cmd ;;
      10) restart_cmd ;;
      11) update_cmd ;;
      12) uninstall_cmd ;;
      13)
        read -r -p "请输入用户名：" username
        read -r -p "请输入设备备注（如 iPhone 13，留空清除）：" note
        modify_user "note" "$username" "$note"
        ;;
      14)
        read -r -p "请输入用户名：" username
        local state
        state="$(python3 - "$USERS_FILE" "$username" <<'PY'
import json, sys
users = json.load(open(sys.argv[1], encoding="utf-8"))
print("enable" if users.get(sys.argv[2], {}).get("disabled") else "disable")
PY
)"
        modify_user "$state" "$username"
        ;;
      99) exit 0 ;;
      *)
        echo "无效选择"
        sleep 1
        ;;
    esac
    echo
    read -r -p "按回车返回菜单..." _
  done
}

# 状态
status_cmd() {
  need_root status
  read_env
  local port_suffix=""
  [ "${PANEL_PORT:-443}" != "443" ] && port_suffix=":${PANEL_PORT}"
  echo "HY2 AIO v${AIO_VERSION:-unknown}"
  echo "面板：https://${DOMAIN}${port_suffix}/${PANEL_PATH}/"
  echo
  systemctl --no-pager --full status \
    hysteria-server.service hy2-aio.service caddy.service \
    | sed -n '1,45p' || true
  echo
  ss -lntup | grep -E ':(80|443|18081|9999)\b' || true
}

# 显示账号
show_cmd() {
  need_root show
  read_env
  write_access_file
  cat "$ACCESS_FILE"
}

# 同步
sync_cmd() {
  need_root sync
  read_env
  api_post sync
  echo
}

# 日志
logs_cmd() {
  need_root logs
  local lines="${1:-120}"
  journalctl -u hysteria-server.service -u hy2-aio.service -u caddy.service \
    --no-pager -n "$lines"
}

# 重启
restart_cmd() {
  need_root restart
  systemctl restart hysteria-server.service hy2-aio.service caddy.service
  sleep 2
  status_cmd
}

# 更新
update_cmd() {
  need_root update
  log "升级 Hysteria 2"
  local tmp script
  tmp="$(mktemp -d)"
  script="$tmp/get-hy2.sh"
  curl -fsSL https://get.hy2.sh/ -o "$script"
  grep -q 'hysteria' "$script" || { rm -rf "$tmp"; die "Hysteria 安装脚本校验失败"; }
  bash "$script"
  rm -rf "$tmp"
  systemctl restart hysteria-server.service
  hysteria version || true
}

# 卸载
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

# 安装主流程
install_stack() {
  need_root install
  have_systemd || die "此脚本需要 systemd"
  [ -f /etc/os-release ] || die "无法识别系统"
  # shellcheck disable=SC1091
  source /etc/os-release
  detect_platform

  if [ -f "$ENV_FILE" ] && [ "${HY2_FORCE:-0}" != "1" ]; then
    die "HY2 AIO 已安装。查看状态：sudo hy2 status"
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
  SPEED_TEST="${HY2_SPEED_TEST:-false}"
  # IP / sslip 证书无法校验真实 SNI，默认 disable；真实域名可设 HY2_SNI_GUARD=strict
  if [ -n "${HY2_SNI_GUARD:-}" ]; then
    SNI_GUARD="$HY2_SNI_GUARD"
  elif [[ "$DOMAIN" == *sslip.io ]] || [[ "$DOMAIN" == "$PUBLIC_IP" ]]; then
    SNI_GUARD="disable"
  else
    SNI_GUARD="strict"
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
SPEED_TEST=$SPEED_TEST
SNI_GUARD=$SNI_GUARD
EOF
  chown root:root "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
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

  # 安装模块到系统目录
  local modules_dir="/usr/local/lib/hy2-aio/modules"
  mkdir -p "$modules_dir/lib" "$modules_dir/bin"
  cp -a "${SCRIPT_DIR}/lib/"* "$modules_dir/lib/"
  cp -a "${SCRIPT_DIR}/bin/"* "$modules_dir/bin/"

  systemctl daemon-reload
  systemctl enable hysteria-server.service hy2-aio.service caddy.service >/dev/null
  systemctl restart hysteria-server.service
  sleep 2
  systemctl restart hy2-aio.service
  systemctl restart caddy.service
  sleep 3
  wait_services

  api_post sync >/dev/null || true

  # 安装系统命令入口
  install -m 0755 "${modules_dir}/bin/hy2.sh" "$SELF_INSTALL"

  write_access_file
  test_https

  local port_suffix=""
  [ "${PANEL_PORT:-443}" != "443" ] && port_suffix=":${PANEL_PORT}"

  echo
  echo "============================================================"
  echo "HY2 AIO 安装完成"
  echo "============================================================"
  echo "面板：https://${DOMAIN}${port_suffix}/${PANEL_PATH}/"
  echo "面板用户名：${PANEL_USER}"
  echo "面板密码：已写入 ${ACCESS_FILE}（不在终端显示）"
  echo "账号资料：${ACCESS_FILE}"
  echo
  echo "常用命令："
  echo "  sudo hy2              # 打开菜单"
  echo "  sudo hy2 status       # 查看状态"
  echo "  sudo hy2 show         # 显示账号"
  echo "  sudo hy2 mode         # 速率模式"
  echo "  sudo hy2 add-user 用户名"
  echo "  sudo hy2 remove-user 用户名"
  echo "  sudo hy2 rotate-user 用户名"
  echo "  sudo hy2 backup       # 备份"
  echo
  echo "云厂商防火墙必须放行：TCP 80、TCP 443、UDP 443"
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
    warn "面板 HTTPS 暂未成功。请确认云厂商防火墙已放行 TCP 80、TCP 443、UDP 443。"
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
  sudo bash hy2.sh install     # 安装
  sudo bash hy2.sh repair      # 修复/升级
  sudo hy2                     # 打开交互菜单

菜单模式：
  sudo hy2                     # 打开菜单

命令模式：
  sudo hy2 status              # 查看状态
  sudo hy2 show                # 显示账号
  sudo hy2 sync                # 同步数据
  sudo hy2 mode                # 速率模式菜单
  sudo hy2 mode show           # 显示当前模式
  sudo hy2 users               # 用户列表
  sudo hy2 add-user <用户名>   # 添加用户
  sudo hy2 remove-user <用户名> # 删除用户
  sudo hy2 rotate-user <用户名> # 轮换密钥
  sudo hy2 note <用户名> [备注] # 设置设备备注（留空清除）
  sudo hy2 disable <用户名>    # 禁用用户
  sudo hy2 enable <用户名>     # 启用用户
  sudo hy2 backup              # 备份
  sudo hy2 logs [行数]         # 查看日志
  sudo hy2 restart             # 重启服务
  sudo hy2 update              # 更新 Hysteria
  sudo hy2 uninstall           # 卸载

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
  HY2_SPEED_TEST      开启 Hysteria speedTest（默认 false）
  HY2_SNI_GUARD       SNI 校验：disable|strict（真实域名默认 strict）
  HY2_BACKUP_DAYS     备份保留天数，默认 14
  HY2_REPO_URL        模块下载地址（默认 GitHub raw）
  HY2_REPO_REF        Git 分支/tag/commit，默认 main（仅默认 URL 时生效）
  HYSTERIA_VERSION    钉死的 Hysteria 版本，默认 v2.12.1
EOF
}

# 主入口
main() {
  # 加载模块
  if [ -f "${SCRIPT_DIR}/lib/core.sh" ]; then
    # 开发模式：本地模块
    load_local_modules
  elif [ -f "/usr/local/lib/hy2-aio/modules/lib/core.sh" ]; then
    # 已安装模式
    load_installed_modules
  elif [ "${1:-}" = "install" ] || [ "${1:-}" = "help" ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    # 安装前：临时下载模块
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    fetch_modules "$tmp_dir"
    SCRIPT_DIR="$tmp_dir"
    load_local_modules
  else
    _bootstrap_die "模块未安装，请运行：sudo bash hy2.sh install"
  fi

  # 解析命令
  local command="${1:-menu}"
  case "$command" in
    menu)       menu_interactive ;;
    install)    install_stack ;;
    repair)     repair_cmd ;;
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
    update)     update_cmd ;;
    uninstall)  uninstall_cmd ;;
    help|-h|--help) usage ;;
    *)          usage; exit 1 ;;
  esac
}

main "$@"
