#!/usr/bin/env bash
# cli.sh - 状态/账号/同步等命令 + 交互菜单

status_cmd() {
  need_root status
  read_env
  local port_suffix="" status_ports
  [ "${PANEL_PORT:-443}" != "443" ] && port_suffix=":${PANEL_PORT}"
  echo "HY2 AIO v${AIO_VERSION:-unknown}"
  echo "面板：https://${DOMAIN}${port_suffix}/${PANEL_PATH}/"
  echo "Hysteria UDP：${HY2_PORT:-443}"
  echo "统计 API：127.0.0.1:${STATS_PORT}"
  echo "面板后端：${BACKEND_HOST}:${BACKEND_PORT}"
  if command -v obfs_is_enabled >/dev/null 2>&1 && obfs_is_enabled; then
    echo "混淆：on (salamander)"
  else
    echo "混淆：off"
  fi
  echo "QUIC 保活：${QUIC_KEEP_ALIVE_PERIOD:-5s} / idle ${QUIC_MAX_IDLE_TIMEOUT:-120s}"
  echo
  systemctl --no-pager --full status \
    hysteria-server.service hy2-aio.service caddy.service \
    | sed -n '1,45p' || true
  echo
  status_ports="${PANEL_PORT}|${STATS_PORT}|${BACKEND_PORT}|${HY2_PORT}"
  ss -lntup | grep -E ":(${status_ports})\\b" || true
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

logs_cmd() {
  need_root logs
  local lines="${1:-120}"
  journalctl -u hysteria-server.service -u hy2-aio.service -u caddy.service \
    --no-pager -n "$lines"
}

restart_cmd() {
  need_root restart
  ensure_hysteria_config_perms
  systemctl restart hysteria-server.service hy2-aio.service caddy.service
  sleep 2
  status_cmd
}

update_cmd() {
  need_root update
  log "升级 Hysteria 2（钉死版本 + SHA256）"
  install_hysteria 1
  systemctl restart hysteria-server.service
  hysteria version || true
}

soft_read_env_for_uninstall() {
  # Uninstall must still work when config.env is missing or historically invalid.
  if [ -f "$ENV_FILE" ]; then
    local line key value
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line#"${line%%[![:space:]]*}"}"
      line="${line%"${line##*[![:space:]]}"}"
      [ -z "$line" ] && continue
      case "$line" in
        \#*) continue ;;
        *=*) ;;
        *) continue ;;
      esac
      key="${line%%=*}"
      value="${line#*=}"
      [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
      printf -v "$key" '%s' "$value"
      export "$key"
    done < "$ENV_FILE"
  fi
  HY2_PORT="${HY2_PORT:-443}"
  PANEL_PORT="${PANEL_PORT:-443}"
  API_SECRET="${API_SECRET:-}"
}

uninstall_cmd() {
  need_root uninstall
  soft_read_env_for_uninstall
  local answer="${HY2_YES:-}" purge="${HY2_PURGE:-0}"
  if [ "$answer" != "1" ]; then
    echo "将停用并移除 HY2 AIO 服务、面板站点、reload 单元与 fail2ban 规则。"
    echo "默认保留：$CONFIG_DIR、$STATE_DIR、$ROLLBACK_DIR、/etc/hysteria"
    echo "彻底删除数据请再用：HY2_PURGE=1 hy2 uninstall"
    read -r -p "确认卸载 HY2 AIO 服务？输入 YES：" answer
    [ "$answer" = "YES" ] || die "已取消"
  fi
  if [ "$purge" = "1" ] && [ "${HY2_YES:-}" != "1" ]; then
    read -r -p "彻底删除配置与数据不可恢复。输入 PURGE 确认：" answer
    [ "$answer" = "PURGE" ] || die "已取消彻底删除"
  fi

  if [ -n "${API_SECRET:-}" ]; then
    api_post backup >/dev/null 2>&1 || true
  fi

  systemctl disable --now \
    hy2-aio.service \
    hy2-aio-reload-hysteria.path \
    hysteria-server.service \
    2>/dev/null || true
  systemctl stop hy2-aio-reload-hysteria.service 2>/dev/null || true

  remove_hy2_cli
  rm -f \
    "$SERVICE_FILE" \
    "$HYSTERIA_SERVICE_FILE" \
    "$RELOAD_PATH_FILE" \
    "$RELOAD_SERVICE_FILE"
  rm -rf "$APP_DIR" "$WEB_DIR"
  rm -f /run/hy2-aio/reload-hysteria

  if declare -F caddyfile_remove_hy2_site >/dev/null 2>&1; then
    caddyfile_remove_hy2_site "$CADDY_FILE" "$CADDY_SITE_FILE"
  else
    rm -f "$CADDY_SITE_FILE"
  fi
  if command -v caddy >/dev/null 2>&1 && [ -f "$CADDY_FILE" ]; then
    caddy validate --config "$CADDY_FILE" >/dev/null 2>&1 \
      && systemctl reload caddy.service 2>/dev/null \
      || systemctl restart caddy.service 2>/dev/null \
      || true
  fi

  if declare -F remove_fail2ban_panel >/dev/null 2>&1; then
    remove_fail2ban_panel
  else
    rm -f /etc/fail2ban/filter.d/hy2-caddy-auth.conf /etc/fail2ban/jail.d/hy2-caddy-auth.conf
  fi
  if declare -F remove_hy2_sysctl >/dev/null 2>&1; then
    remove_hy2_sysctl
  else
    rm -f /etc/sysctl.d/99-hy2-aio.conf
  fi
  if declare -F remove_hy2_firewall_rules >/dev/null 2>&1; then
    remove_hy2_firewall_rules || true
  fi

  systemctl daemon-reload 2>/dev/null || true

  if [ "$purge" = "1" ]; then
    rm -rf "$CONFIG_DIR" "$STATE_DIR" "$ROLLBACK_DIR" "$HYSTERIA_DIR"
    rm -f "$ACCESS_FILE"
    rm -f /var/log/caddy/hy2-aio.log /var/log/caddy/hy2-aio.log.* 2>/dev/null || true
    log "已彻底卸载：服务、站点片段与配置/数据均已删除"
  else
    warn "已卸载服务与站点残留；保留配置与数据：$CONFIG_DIR、$STATE_DIR、$ROLLBACK_DIR、/etc/hysteria"
    warn "彻底删除数据：HY2_PURGE=1 hy2 uninstall"
  fi
  warn "Caddy / Hysteria 二进制未卸载；防火墙 80/tcp（若曾放行）可能仍保留"
}

menu_call() {
  local fn="$1"
  shift || true
  if ! declare -F "$fn" >/dev/null 2>&1; then
    echo "当前版本缺少命令：$fn"
    echo "请先执行：hy2 upgrade"
    return 1
  fi
  "$fn" "$@"
}

menu_toggle_user() {
  local username="" state
  read -r -p "请输入用户名：" username
  [ -n "$username" ] || { echo "用户名不能为空"; return 1; }
  [ -f "$USERS_FILE" ] || { echo "找不到用户文件"; return 1; }
  state="$(python3 - "$USERS_FILE" "$username" <<'PY'
import json, sys
path, name = sys.argv[1], sys.argv[2]
users = json.load(open(path, encoding="utf-8"))
if name not in users:
    raise SystemExit(f"用户不存在：{name}")
print("enable" if users[name].get("disabled") else "disable")
PY
)" || return 1
  modify_user "$state" "$username"
}

menu_install_help() {
  if [ -f "${ENV_FILE:-/etc/hy2-aio/config.env}" ]; then
    echo "本机已安装，不能重复 install。"
    echo "跨版本升级请选「1) 升级 HY2 AIO」，或执行：hy2 upgrade && hy2 restart"
    return 0
  fi
  if declare -F install_stack >/dev/null 2>&1; then
    install_stack
    return $?
  fi
  echo "新机安装请执行："
  echo "  curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v${SCRIPT_VERSION}/hy2.sh -o hy2.sh"
  echo "  bash hy2.sh install"
}

menu_upgrade() {
  local hy2_bin="${SELF_INSTALL:-/usr/local/bin/hy2}" bootstrap=""
  if [ -x "$hy2_bin" ]; then
    # 不用 exec，升级完还能回菜单
    "$hy2_bin" upgrade
    return $?
  fi
  # Re-enter bootstrap so upgrade fetches remote modules instead of repairing this checkout.
  if [ -f "${SCRIPT_DIR}/hy2.sh" ]; then
    bootstrap="${SCRIPT_DIR}/hy2.sh"
  elif [ -f "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/hy2.sh" ]; then
    bootstrap="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/hy2.sh"
  fi
  if [ -n "$bootstrap" ]; then
    bash "$bootstrap" upgrade
    return $?
  fi
  echo "请执行：hy2 upgrade"
  return 1
}

show_menu() {
  clear
  cat <<EOF
 _   _ ____   __     _____ ___
| | | |___ \  \ \   / /_ _|_ _|
| |_| | __) |  \ \ / / | | | |
|  _  |/ __/    \ V /  | | | |
|_| |_|_____|    \_/  |___|___|

HY2 AIO v${AIO_VERSION:-?}  管理菜单

EOF
  echo "── 维护 ──────────────────────────"
  echo "  1) 升级 HY2 AIO（拉最新版，推荐）"
  echo "  2) 修复配置（repair）"
  echo "  3) 更新 Hysteria 内核"
  echo "  4) 重启服务"
  echo "  5) 状态"
  echo
  echo "── 账号 ──────────────────────────"
  echo "  6) 显示账号/订阅"
  echo "  7) 用户列表"
  echo "  8) 添加用户"
  echo "  9) 删除用户"
  echo " 10) 轮换用户密钥"
  echo " 11) 设置备注"
  echo " 12) 禁用/启用用户"
  echo
  echo "── 功能 ──────────────────────────"
  echo " 13) 速率模式"
  echo " 14) 混淆开关（obfs）"
  echo " 15) 同步数据"
  echo " 16) 备份"
  echo " 17) 回滚最近快照"
  echo " 18) 日志"
  echo
  echo "── 其他 ──────────────────────────"
  echo " 19) 安装说明（仅新机）"
  echo " 20) 卸载"
  echo " 99) 退出"
  echo
}

menu_interactive() {
  local choice username note obfs_choice
  while true; do
    show_menu
    read -r -p "请选择 [1-20/99]: " choice
    case "$choice" in
      1)  menu_upgrade ;;
      2)  menu_call repair_cmd ;;
      3)  menu_call update_cmd ;;
      4)  menu_call restart_cmd ;;
      5)  menu_call status_cmd ;;
      6)  menu_call show_cmd ;;
      7)  menu_call users_cmd ;;
      8)
        read -r -p "请输入用户名：" username
        menu_call modify_user "add-user" "$username"
        ;;
      9)
        read -r -p "请输入用户名：" username
        menu_call modify_user "remove-user" "$username"
        ;;
      10)
        read -r -p "请输入用户名：" username
        menu_call modify_user "rotate-user" "$username"
        ;;
      11)
        read -r -p "请输入用户名：" username
        read -r -p "请输入设备备注（留空清除）：" note
        menu_call modify_user "note" "$username" "$note"
        ;;
      12) menu_toggle_user ;;
      13) menu_call mode_interactive ;;
      14)
        echo "0) 查看状态  1) 开启混淆  2) 关闭混淆"
        read -r -p "请选择 [0-2]: " obfs_choice
        case "$obfs_choice" in
          0) menu_call obfs_cmd show ;;
          1) menu_call obfs_cmd on ;;
          2) menu_call obfs_cmd off ;;
          *) echo "无效选择" ;;
        esac
        ;;
      15) menu_call sync_cmd ;;
      16) menu_call backup_cmd ;;
      17) menu_call rollback_cmd ;;
      18) menu_call logs_cmd ;;
      19) menu_install_help ;;
      20) menu_call uninstall_cmd ;;
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
