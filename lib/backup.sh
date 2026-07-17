#!/usr/bin/env bash
# backup.sh - 备份、恢复、回滚

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
  [ -n "$snapshot" ] || die "未找到回滚快照"
  echo "最新快照：$snapshot"
  echo "0. 恢复"
  echo "1. 取消"
  local choice
  read -r -p "请选择 [0/1]: " choice
  [ "$choice" = "0" ] || return 0
  tar -xzf "$snapshot" -C /
  systemctl daemon-reload
  systemctl restart hysteria-server.service hy2-aio.service caddy.service || true
  log "回滚完成"
}

repair_cmd() {
  need_root repair
  read_env
  log "回滚快照：$(snapshot_before_change)"

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
  echo "运行速率模式菜单：sudo hy2 mode"
}

backup_cmd() {
  need_root backup
  read_env
  api_post backup
  echo
}
