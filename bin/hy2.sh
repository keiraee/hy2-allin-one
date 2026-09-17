#!/usr/bin/env bash
# hy2 - HY2 AIO 命令入口（安装到 /usr/local/bin/hy2）

set -Eeuo pipefail
umask 077

MODULES_DIR="/usr/local/lib/hy2-aio/modules"
SCRIPT_DIR="$MODULES_DIR"
DEFAULT_REPO_SLUG="keiraee/hy2-allin-one"
REPO_SLUG="${HY2_REPO:-$DEFAULT_REPO_SLUG}"

# 自更新：先拉最新引导脚本再 repair，不依赖本机旧模块里的逻辑
if [ "${1:-}" = "upgrade" ]; then
  [ "$(id -u)" -eq 0 ] || { printf '%s\n' "需要 root。已是 root：hy2 upgrade；有 sudo：sudo hy2 upgrade" >&2; exit 1; }
  env_file="${HY2_ENV_FILE:-/etc/hy2-aio/config.env}"
  ref="${HY2_REPO_REF:-}"
  persist=""
  if [ -z "$ref" ] && [ -f "$env_file" ]; then
    ref="$(awk -F= '/^HY2_TRACK_REF=/{gsub(/\r/,""); print $2; exit}' "$env_file" || true)"
  fi
  if [ -z "$ref" ] || [ "$ref" = "latest" ]; then
    persist="latest"
    ref="$(curl -fsSL -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
      "https://api.github.com/repos/${REPO_SLUG}/releases/latest" \
      | python3 -c 'import sys, json; print(json.load(sys.stdin)["tag_name"])')" \
      || { printf '%s\n' "无法获取 latest release（${REPO_SLUG}）" >&2; exit 1; }
  else
    persist="$ref"
  fi
  [ -n "$ref" ] || { printf '%s\n' "upgrade 目标为空" >&2; exit 1; }
  current="未知"
  if [ -f "$env_file" ]; then
    current="$(awk -F= '/^AIO_VERSION=/{gsub(/\r/,""); print $2; exit}' "$env_file" || true)"
    [ -n "$current" ] || current="未知"
  fi
  case "$current" in
    未知) ;;
    v*) ;;
    [0-9]*) current="v${current}" ;;
  esac
  target="$ref"
  case "$target" in
    v*) ;;
    [0-9]*) target="v${target}" ;;
  esac
  skip=0
  case "$ref" in
    v[0-9]*|[0-9]*)
      if [ "$current" != "未知" ] && [ "$current" = "$target" ]; then
        skip=1
      fi
      ;;
  esac
  if [ "$skip" -eq 1 ]; then
    printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "已是 ${current}，无需升级"
    exit 0
  fi
  fetch_ref="$ref"
  raw_base=""
  if [ -n "${HY2_REPO_URL:-}" ]; then
    raw_base="${HY2_REPO_URL%/}"
    bootstrap_url="${raw_base}/hy2.sh"
  else
    if ! printf '%s' "$ref" | grep -qiE '^[0-9a-f]{40}$' \
      && ! printf '%s' "$ref" | grep -qE '^v?[0-9]+(\.[0-9]+)*([.-][0-9A-Za-z]+)*$'; then
      sha="$(curl -fsSL -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
        "https://api.github.com/repos/${REPO_SLUG}/commits/${ref}" \
        | python3 -c 'import sys, json; print(json.load(sys.stdin).get("sha") or "")')" \
        || { printf '%s\n' "无法解析 Git 引用 ${REPO_SLUG}@${ref}" >&2; exit 1; }
      printf '%s' "$sha" | grep -qiE '^[0-9a-f]{40}$' \
        || { printf '%s\n' "GitHub 返回的 sha 无效：${sha}" >&2; exit 1; }
      printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "钉住提交：${ref} → ${sha:0:12}"
      fetch_ref="$sha"
    fi
    raw_base="https://raw.githubusercontent.com/${REPO_SLUG}/${fetch_ref}"
    bootstrap_url="${raw_base}/hy2.sh"
  fi
  printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "升级 ${current} → ${target}"
  printf '\033[1;36m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "引导脚本：${bootstrap_url}"
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
    "${bootstrap_url}?nocache=$(date +%s)" -o "$tmp/hy2.sh" \
    || { printf '%s\n' "下载 hy2.sh 失败" >&2; exit 1; }
  HY2_REPO="$REPO_SLUG" HY2_REPO_REF="$ref" HY2_REPO_URL="${HY2_REPO_URL:-$raw_base}" \
    HY2_PERSIST_TRACK="$persist" HY2_UPGRADE_BANNER=1 \
    bash "$tmp/hy2.sh" repair
  exit $?
fi

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
source "${MODULES_DIR}/lib/cli.sh"

usage() {
  cat <<EOF
HY2 AIO v${AIO_VERSION}

用法：
  hy2                     # 打开交互菜单（需 root）

说明：管理命令需要 root。已是 root 直接 hy2；有 sudo 的系统可写 sudo hy2。

命令模式：
  hy2 status              # 查看状态
  hy2 show                # 显示账号
  hy2 panel               # 查看面板账号和密码
  hy2 sync                # 同步数据
  hy2 mode                # 速率模式菜单
  hy2 mode show           # 显示当前模式
  hy2 users               # 用户列表
  hy2 add-user <用户名>   # 添加用户
  hy2 remove-user <用户名> # 删除用户
  hy2 rotate-user <用户名> # 轮换密钥
  hy2 note <用户名> [备注] # 设置设备备注（留空清除）
  hy2 disable <用户名>    # 禁用用户
  hy2 enable <用户名>     # 启用用户
  hy2 on                  # 开启 Hysteria（需至少一个已启用用户）
  hy2 off                 # 关闭 Hysteria（停监听，不删用户）
  hy2 backup              # 备份
  hy2 rollback            # 回滚最近快照
  hy2 logs [行数]         # 查看日志
  hy2 restart             # 重启 Hysteria + 面板后端 + Caddy
  hy2 update              # 更新 Hysteria
  hy2 upgrade             # 升级 HY2 AIO 到 GitHub 最新版
  hy2 repair              # 用当前已装模块修复
  hy2 uninstall           # 卸载（保留配置；彻底删除用 HY2_PURGE=1）
  hy2 obfs show           # 查看混淆状态
  hy2 obfs on|off         # 开启/关闭 Salamander 混淆
  hy2 help|-h|--help|-help
EOF
}

command="${1:-menu}"
case "$command" in
  menu)       menu_interactive ;;
  install)    die "请使用 bash hy2.sh install 安装" ;;
  repair)     repair_cmd ;;
  upgrade)    die "内部错误：upgrade 应在加载模块前处理" ;;
  status)     status_cmd ;;
  show)       show_cmd ;;
  panel)      panel_cmd ;;
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
