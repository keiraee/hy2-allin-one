#!/usr/bin/env bash
# hy2 - HY2 AIO 命令入口（安装到 /usr/local/sbin/hy2）

set -Eeuo pipefail
umask 077

MODULES_DIR="/usr/local/lib/hy2-aio/modules"

# 加载模块
source "${MODULES_DIR}/lib/core.sh"
source "${MODULES_DIR}/lib/install.sh"
source "${MODULES_DIR}/lib/config.sh"
source "${MODULES_DIR}/lib/panel.sh"
source "${MODULES_DIR}/lib/user.sh"
source "${MODULES_DIR}/lib/cert.sh"
source "${MODULES_DIR}/lib/access.sh"
source "${MODULES_DIR}/lib/backup.sh"
source "${MODULES_DIR}/lib/mode.sh"
source "${MODULES_DIR}/lib/backend.sh"

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
  log "升级 Hysteria 2（钉死版本 + SHA256）"
  install_hysteria 1
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

usage() {
  cat <<EOF
HY2 AIO v${AIO_VERSION}

用法：
  sudo hy2                     # 打开交互菜单

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
  sudo hy2 repair              # 修复/升级
EOF
}

# 主入口
command="${1:-menu}"
case "$command" in
  menu)       menu_interactive ;;
  install)    die "请使用 bash hy2.sh install 安装" ;;
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
