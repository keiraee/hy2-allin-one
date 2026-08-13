#!/usr/bin/env bash
# backup.sh - 备份、恢复、回滚

rollback_artifacts() {
  printf '%s\n' \
    "$CONFIG_DIR" \
    "$HYSTERIA_DIR" \
    "$APP_DIR" \
    "$WEB_DIR" \
    "$CADDY_FILE" \
    "$CADDY_SITE_FILE" \
    "$SERVICE_FILE" \
    "$HYSTERIA_SERVICE_FILE" \
    "$RELOAD_PATH_FILE" \
    "$RELOAD_SERVICE_FILE" \
    "$HYSTERIA_DROPIN_DIR" \
    "$SELF_INSTALL" \
    "$SELF_INSTALL_SBIN"
}

ensure_rollback_dir() {
  [ ! -L "$ROLLBACK_DIR" ] || die "回滚目录不能是符号链接：$ROLLBACK_DIR"
  install -d -o root -g root -m 0700 "$ROLLBACK_DIR"
  [ "$(stat -c '%u' "$ROLLBACK_DIR")" = "0" ] \
    || die "回滚目录必须归 root 所有：$ROLLBACK_DIR"
  [ "$(stat -c '%a' "$ROLLBACK_DIR")" = "700" ] \
    || die "回滚目录权限必须为 0700：$ROLLBACK_DIR"
}

validate_rollback_members() {
  local snapshot="$1" artifact
  local artifacts=()
  while IFS= read -r artifact; do
    artifacts+=("$artifact")
  done < <(rollback_artifacts)
  python3 - "$snapshot" "${artifacts[@]}" <<'PY'
import posixpath
import sys
import tarfile
from pathlib import PurePosixPath

snapshot = sys.argv[1]
allowed = tuple(path.lstrip("/").rstrip("/") for path in sys.argv[2:])


def fail(message: str) -> None:
    raise SystemExit(message)


def normalize_member(name: str, *, label: str) -> str:
    if not name or name.startswith("/"):
        fail(f"危险{label}：{name!r}")
    value = name.rstrip("/")
    path = PurePosixPath(value)
    if any(part in ("", ".", "..") for part in path.parts):
        fail(f"危险{label}：{name!r}")
    normalized = posixpath.normpath(value)
    if normalized != value:
        fail(f"危险{label}：{name!r}")
    return normalized


def is_allowed(path: str) -> bool:
    return any(path == root or path.startswith(root + "/") for root in allowed)


seen: set[str] = set()
try:
    archive = tarfile.open(snapshot, "r:gz")
except (OSError, tarfile.TarError) as exc:
    fail(f"回滚归档无法读取：{exc}")

with archive:
    members = archive.getmembers()
    if not members:
        fail("回滚归档没有成员")
    for member in members:
        name = normalize_member(member.name, label="归档成员")
        if name in seen:
            fail(f"归档成员重复：{name}")
        seen.add(name)
        if not is_allowed(name):
            fail(f"归档成员不在安装产物白名单：{name}")
        if member.isreg() or member.isdir():
            continue
        if member.issym() or member.islnk():
            target_raw = member.linkname
            if not target_raw or ".." in PurePosixPath(target_raw).parts:
                fail(f"危险归档链接：{name} -> {target_raw!r}")
            if target_raw.startswith("/"):
                target = target_raw.lstrip("/")
            elif member.issym():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), target_raw))
            else:
                target = posixpath.normpath(target_raw)
            target = normalize_member(target, label="归档链接")
            if not is_allowed(target):
                fail(f"归档链接越过安装产物白名单：{name} -> {target_raw}")
            continue
        fail(f"归档成员类型不安全：{name}")
PY
}

validate_rollback_snapshot() {
  local snapshot="$1" sidecar expected actual resolved_dir resolved_snapshot
  ensure_rollback_dir
  [ -f "$snapshot" ] && [ ! -L "$snapshot" ] || die "回滚归档不是普通文件：$snapshot"
  resolved_dir="$(readlink -f "$ROLLBACK_DIR")"
  resolved_snapshot="$(readlink -f "$snapshot")"
  [ "$(dirname "$resolved_snapshot")" = "$resolved_dir" ] \
    || die "回滚归档不在受信目录：$snapshot"
  [[ "$(basename "$snapshot")" =~ ^hy2-before-[0-9]{8}-[0-9]{6}\.tar\.gz$ ]] \
    || die "回滚归档文件名无效：$snapshot"
  [ "$(stat -c '%u' "$snapshot")" = "0" ] && [ "$(stat -c '%a' "$snapshot")" = "600" ] \
    || die "回滚归档必须为 root:root 且权限为 0600：$snapshot"

  sidecar="${snapshot}.sha256"
  [ -f "$sidecar" ] && [ ! -L "$sidecar" ] || die "回滚归档缺少 SHA256 摘要：$sidecar"
  [ "$(stat -c '%u' "$sidecar")" = "0" ] && [ "$(stat -c '%a' "$sidecar")" = "600" ] \
    || die "回滚摘要必须为 root:root 且权限为 0600：$sidecar"
  expected="$(tr -d '[:space:]' < "$sidecar")"
  [[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || die "回滚 SHA256 摘要格式无效"
  actual="$(sha256sum "$snapshot" | awk '{print $1}')"
  [ "${actual,,}" = "${expected,,}" ] || die "回滚归档 SHA256 校验失败"
  validate_rollback_members "$snapshot" || die "回滚归档成员校验失败"
}

snapshot_before_change() {
  ensure_rollback_dir
  local snapshot="$ROLLBACK_DIR/hy2-before-$(date +%Y%m%d-%H%M%S).tar.gz"
  local temporary="${snapshot}.tmp.$$" sidecar="${snapshot}.sha256" artifact digest
  local artifacts=()
  while IFS= read -r artifact; do
    [ -e "$artifact" ] || [ -L "$artifact" ] || continue
    artifacts+=("$artifact")
  done < <(rollback_artifacts)
  [ "${#artifacts[@]}" -gt 0 ] || die "没有可写入回滚快照的安装产物"
  if ! tar -czf "$temporary" -- "${artifacts[@]}"; then
    rm -f "$temporary"
    die "创建回滚快照失败"
  fi
  chmod 600 "$temporary"
  validate_rollback_members "$temporary" || { rm -f "$temporary"; die "回滚快照成员校验失败"; }
  digest="$(sha256sum "$temporary" | awk '{print $1}')"
  printf '%s\n' "$digest" > "${sidecar}.tmp.$$"
  chmod 600 "${sidecar}.tmp.$$"
  mv -f "$temporary" "$snapshot"
  mv -f "${sidecar}.tmp.$$" "$sidecar"
  # Keep only the newest 10 rollback snapshots.
  local old
  # shellcheck disable=SC2012
  ls -1t "$ROLLBACK_DIR"/hy2-before-*.tar.gz 2>/dev/null | tail -n +11 | while read -r old; do
    rm -f "$old" "${old}.sha256"
  done
  printf '%s\n' "$snapshot"
}

rollback_cmd() {
  need_root rollback
  read_env
  local snapshot
  ensure_rollback_dir
  snapshot="$(find "$ROLLBACK_DIR" -maxdepth 1 -type f -name 'hy2-before-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | sed -n '1s/^[^ ]* //p')"
  [ -n "$snapshot" ] || die "未找到回滚快照"
  validate_rollback_snapshot "$snapshot"
  echo "最新快照：$snapshot"
  echo "0. 恢复"
  echo "1. 取消"
  local choice
  read -r -p "请选择 [0/1]: " choice
  [ "$choice" = "0" ] || return 0
  tar -xzf "$snapshot" -C /
  systemctl daemon-reload
  systemctl enable hy2-aio-reload-hysteria.path >/dev/null || true
  systemctl restart hy2-aio-reload-hysteria.path || true
  systemctl restart hysteria-server.service hy2-aio.service caddy.service || true
  log "回滚完成"
}

repair_cmd() {
  need_root repair
  read_env
  local from_version="${AIO_VERSION:-未知}"
  from_version="${from_version#v}"
  log "回滚快照：$(snapshot_before_change)"

  log "升级/修复 HY2 AIO 管理组件"
  ensure_hy2_aio_user
  chown hy2-aio:hy2-aio "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  chmod 0640 "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  ensure_mode_file
  ensure_hysteria_config_perms

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
  chmod 0660 "$HYSTERIA_CONFIG" 2>/dev/null || true

  write_backend
  write_panel
  write_systemd
  write_caddy
  ensure_hy2_aio_user

  # Install CLI before service restarts so a later Caddy failure still leaves `hy2` usable.
  local modules_dir src
  modules_dir="/usr/local/lib/hy2-aio/modules"
  src="${SCRIPT_DIR:-$modules_dir}"
  [ -f "${src}/lib/core.sh" ] || die "找不到模块源：${src}/lib/core.sh（请用：bash hy2.sh repair 或 hy2 upgrade）"
  [ -f "${src}/bin/hy2.sh" ] || die "找不到模块源：${src}/bin/hy2.sh"
  mkdir -p "$modules_dir/lib" "$modules_dir/bin"
  cp -a "${src}/lib/"* "$modules_dir/lib/"
  cp -a "${src}/bin/"* "$modules_dir/bin/"
  install_hy2_cli "${modules_dir}/bin/hy2.sh"

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
      die "Caddy 重载失败（hy2 已安装；修好 Caddy 后执行：hy2 repair）"
    fi
  fi

  sleep 2
  systemctl is-active --quiet hy2-aio.service || die "HY2 AIO 后端未运行"
  api_post sync >/dev/null || true
  write_access_file

  local to_version="${SCRIPT_VERSION#v}"
  if [ "$from_version" = "未知" ]; then
    log "已升级到 v${to_version}"
  elif [ "$from_version" = "$to_version" ]; then
    log "已修复，版本仍为 v${to_version}"
  else
    log "已从 v${from_version} 升级到 v${to_version}"
  fi
  log "已写入 QUIC 保活与混淆开关到配置；Hysteria 未自动重启"
  log "使配置生效：hy2 restart   （或 hy2 obfs on|off）"
  echo "运行速率模式菜单：hy2 mode"
}

backup_cmd() {
  need_root backup
  read_env
  api_post backup
  echo
}
