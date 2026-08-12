#!/usr/bin/env bash
# backup.sh - 备份、恢复、回滚

snapshot_before_change() {
  install -d -m 0700 "$STATE_DIR/rollbacks"
  local snapshot="$STATE_DIR/rollbacks/hy2-before-$(date +%Y%m%d-%H%M%S).tar.gz"
  tar -czf "$snapshot" --ignore-failed-read \
    "$CONFIG_DIR" /etc/hysteria "$APP_DIR" "$WEB_DIR" "$CADDY_FILE" \
    "$SERVICE_FILE" /etc/systemd/system/hysteria-server.service
  chmod 600 "$snapshot"
  # Keep only the newest 10 rollback snapshots.
  local old
  # shellcheck disable=SC2012
  ls -1t "$STATE_DIR/rollbacks"/hy2-before-*.tar.gz 2>/dev/null | tail -n +11 | while read -r old; do
    rm -f "$old"
  done
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
  ensure_hy2_aio_user
  chown hy2-aio:hy2-aio "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  chmod 0640 "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  ensure_mode_file

  python3 - "$ENV_FILE" "$SCRIPT_VERSION" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
found_version = False
found_obfs = False
found_keep = False
found_idle = False
output = []
for line in lines:
    if line.startswith("AIO_VERSION="):
        output.append(f"AIO_VERSION={version}")
        found_version = True
    elif line.startswith("OBFS_ENABLED="):
        output.append(line)
        found_obfs = True
    elif line.startswith("QUIC_KEEP_ALIVE_PERIOD="):
        output.append(line)
        found_keep = True
    elif line.startswith("QUIC_MAX_IDLE_TIMEOUT="):
        output.append(line)
        found_idle = True
    else:
        output.append(line)
if not found_version:
    output.insert(0, f"AIO_VERSION={version}")
if not found_obfs:
    output.append("OBFS_ENABLED=true")
if not found_keep:
    output.append("QUIC_KEEP_ALIVE_PERIOD=5s")
if not found_idle:
    output.append("QUIC_MAX_IDLE_TIMEOUT=120s")
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
os.replace(temporary, path)
PY
  chown root:hy2-aio "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  read_env

  write_rebuild_helper
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG" 2>/dev/null || true
  chmod 0640 "$HYSTERIA_CONFIG" 2>/dev/null || true

  write_backend
  write_panel
  write_systemd
  write_caddy
  ensure_hy2_aio_user

  # Install CLI before service restarts so a later Caddy failure still leaves `hy2` usable.
  local modules_dir
  modules_dir="/usr/local/lib/hy2-aio/modules"
  mkdir -p "$modules_dir/lib" "$modules_dir/bin"
  cp -a "${SCRIPT_DIR}/lib/"* "$modules_dir/lib/"
  cp -a "${SCRIPT_DIR}/bin/"* "$modules_dir/bin/"
  install -m 0755 "${modules_dir}/bin/hy2.sh" "$SELF_INSTALL"

  systemctl daemon-reload
  systemctl enable hy2-aio.service hy2-aio-reload-hysteria.path >/dev/null
  systemctl start hy2-aio-reload-hysteria.path || true

  if ! systemctl restart hy2-aio.service; then
    journalctl -u hy2-aio.service --no-pager -n 100 >&2 || true
    die "HY2 AIO 后端升级失败"
  fi
  systemctl start hy2-aio-reload-hysteria.path || true

  if ! systemctl reload caddy.service 2>/dev/null; then
    if ! systemctl restart caddy.service; then
      journalctl -u caddy.service --no-pager -n 80 >&2 || true
      die "Caddy 重载失败（hy2 命令已安装；修好 Caddy 后执行：sudo hy2 repair）"
    fi
  fi

  sleep 2
  systemctl is-active --quiet hy2-aio.service || die "HY2 AIO 后端未运行"
  api_post sync >/dev/null || true
  write_access_file

  log "HY2 AIO 已升级到 v${SCRIPT_VERSION}"
  log "已写入 QUIC 保活与混淆开关到配置；Hysteria 未自动重启"
  log "使配置生效：sudo hy2 restart   （或 sudo hy2 obfs on|off）"
  echo "运行速率模式菜单：sudo hy2 mode"
}

backup_cmd() {
  need_root backup
  read_env
  api_post backup
  echo
}
