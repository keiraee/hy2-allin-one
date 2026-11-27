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
    "$XRAY_SERVICE_FILE" \
    "$RELOAD_PATH_FILE" \
    "$RELOAD_SERVICE_FILE" \
    "$XRAY_RELOAD_PATH_FILE" \
    "$XRAY_RELOAD_SERVICE_FILE" \
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
  chmod 0600 "$temporary"
  validate_rollback_members "$temporary" || { rm -f "$temporary"; die "回滚快照成员校验失败"; }
  digest="$(sha256sum "$temporary" | awk '{print $1}')"
  printf '%s\n' "$digest" > "${sidecar}.tmp.$$"
  chmod 0600 "${sidecar}.tmp.$$"
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
  local snapshot choice=""
  # 非交互下不能静默“取消成功”——调用方会误以为已回滚；脚本请显式 HY2_YES=1。
  if [ ! -t 0 ] && [ "${HY2_YES:-}" != "1" ]; then
    die "回滚需要交互确认；脚本请用：HY2_YES=1 hy2 rollback"
  fi
  ensure_rollback_dir
  snapshot="$(find "$ROLLBACK_DIR" -maxdepth 1 -type f -name 'hy2-before-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | sed -n '1s/^[^ ]* //p')"
  [ -n "$snapshot" ] || die "未找到回滚快照"
  validate_rollback_snapshot "$snapshot"
  echo "最新快照：$snapshot"
  echo "0. 恢复"
  echo "1. 取消"
  if [ "${HY2_YES:-}" = "1" ]; then
    choice="0"
  else
    read -r -p "请选择 [0/1]: " choice || choice="1"
  fi
  [ "$choice" = "0" ] || { log "已取消回滚"; return 0; }
  tar -xzf "$snapshot" -C /
  systemctl daemon-reload
  systemctl enable hy2-aio-reload-hysteria.path hy2-aio-reload-xray.path >/dev/null || true
  systemctl restart hy2-aio-reload-hysteria.path hy2-aio-reload-xray.path || true
  systemctl restart hysteria-server.service || true
  systemctl restart hy2-aio.service || true
  systemctl restart hy2-xray.service || true
  systemctl restart caddy.service || true
  log "回滚完成"
}

# repair_cmd [force_kernel]
#
# force_kernel=1 时强制重装/升级 Hysteria 内核（hy2 upgrade 走这条），
# 否则只在缺失时补装（hy2 repair 走这条 —— 修复不该在用户不知情时换内核）。
repair_cmd() {
  need_root repair
  local force_kernel="${1:-0}"
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

  # 写入带构建信息的完整版本,不再写纯基础号 ——
  # 否则每次 upgrade 后面板都显示同一个 1.7.3,版本号"固定"不动。
  #
  # ⚠️ 不能用内存里的 $AIO_VERSION 做判据!read_env 会把 config.env 里
  # 上次写入的 AIO_VERSION(如 1.7.3.4f40b4e)覆盖进内存,它永远≠
  # SCRIPT_VERSION,导致 FETCH_COMMIT 永远拼不上去 → 版本卡死在旧提交。
  #
  # 三条轨道的版本语义(小k 质疑后推演清楚):
  #   main 轨道: modules=tarball 无 .git → core.sh git 探测失效,
  #     core.sh 里 AIO_VERSION=纯基础号 → 拼 HY2_FETCH_COMMIT(本次提交)
  #     → main 每推一版,upgrade 一次版本就变一次。
  #   release 轨道: tag tarball 里 SCRIPT_VERSION 已 bump(如 1.8.0)
  #     → 同拼 FETCH_COMMIT → 1.8.0.<taghash>。
  #   开发机: git checkout → core.sh 已拼好 .N.gHASH,
  #     但 repair_cmd 必须以【本次部署的提交】为准 → 一律用
  #     SCRIPT_VERSION + FETCH_COMMIT,这样部署结果和拉取源强一致。
  local full_version="$SCRIPT_VERSION"
  if [ -n "${HY2_FETCH_COMMIT:-}" ]; then
    full_version="$SCRIPT_VERSION.${HY2_FETCH_COMMIT:0:7}"
  elif [ -n "$AIO_VERSION" ] && [ "$AIO_VERSION" != "$SCRIPT_VERSION" ]; then
    # 拿不到 FETCH_COMMIT(本地开发直装)才退回 core.sh 的构建版本
    full_version="$AIO_VERSION"
  fi
  python3 - "$ENV_FILE" "$full_version" "${HY2_PERSIST_TRACK:-}" "${HY2_FETCH_MODULES_SHA:-}" "${HY2_FETCH_COMMIT:-}" <<'PY'
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
track = sys.argv[3] if len(sys.argv) > 3 else ""
modules_sha = sys.argv[4] if len(sys.argv) > 4 else ""
repo_sha = sys.argv[5] if len(sys.argv) > 5 else ""
if not re.fullmatch(r"[0-9a-fA-F]{40}", repo_sha or ""):
    repo_sha = ""
lines = path.read_text(encoding="utf-8").splitlines()
found_version = False
found_obfs = False
found_keep = False
found_idle = False
found_track = False
found_modules = False
found_repo_sha = False
output = []
for line in lines:
    if line.startswith("AIO_VERSION="):
        output.append(f"AIO_VERSION={version}")
        found_version = True
    elif line.startswith("HY2_TRACK_REF="):
        if track == "latest":
            continue
        if track:
            output.append(f"HY2_TRACK_REF={track}")
            found_track = True
        else:
            output.append(line)
            found_track = True
    elif line.startswith("HY2_MODULES_SHA="):
        output.append(f"HY2_MODULES_SHA={modules_sha}" if modules_sha else line)
        found_modules = True
    elif line.startswith("HY2_REPO_SHA="):
        if modules_sha:
            if repo_sha:
                output.append(f"HY2_REPO_SHA={repo_sha}")
            found_repo_sha = True
        else:
            output.append(line)
            found_repo_sha = True
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
if track and track != "latest" and not found_track:
    output.append(f"HY2_TRACK_REF={track}")
if modules_sha and not found_modules:
    output.append(f"HY2_MODULES_SHA={modules_sha}")
if repo_sha and not found_repo_sha:
    output.append(f"HY2_REPO_SHA={repo_sha}")
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

  # 补齐缺失组件：安装中途失败后 repair 可直接续装（已装则跳过）
  ensure_hysteria_user
  install_hysteria "$force_kernel"
  install_xray
  install_caddy_v12
  ensure_reality_env
  read_env

  # 刷新 Hysteria 证书：Caddy 可能刚续了 Let's Encrypt，或者这台机器是从
  # 老版本升上来的（那时只有自签证书）。create_certificate 内部会优先复用
  # Caddy 的真证书，拿不到才自签，所以这里无条件调用一次是安全的。
  # 少了这一步，升级后 Hysteria 会一直用旧证书，客户端严格校验就过不去。
  create_certificate || warn "证书刷新失败（沿用现有证书）"

  ensure_users_vless_ids

  write_rebuild_helper
  write_xray_rebuild_helper
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG" 2>/dev/null || true
  chmod 0660 "$HYSTERIA_CONFIG" 2>/dev/null || true
  "$XRAY_REBUILD_FILE"
  chown hy2-aio:hy2-aio "$XRAY_CONFIG" 2>/dev/null || true
  chmod 0640 "$XRAY_CONFIG" 2>/dev/null || true

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
  if [ -d "${src}/assets" ] && [ "${src}/assets" != "${modules_dir}/assets" ]; then
    mkdir -p "$modules_dir/assets"
    cp -a "${src}/assets/." "$modules_dir/assets/"
  fi
  if [ -d "${src}/web" ] && [ "${src}/web" != "${modules_dir}/web" ]; then
    mkdir -p "$modules_dir/web"
    cp -a "${src}/web/." "$modules_dir/web/"
  fi
  if [ -d "${src}/app" ] && [ "${src}/app" != "${modules_dir}/app" ]; then
    mkdir -p "$modules_dir/app"
    cp -a "${src}/app/." "$modules_dir/app/"
  fi
  install_hy2_cli "${modules_dir}/bin/hy2.sh"

  systemctl daemon-reload
  systemctl enable hy2-aio.service hy2-aio-reload-hysteria.path hy2-xray.service hy2-aio-reload-xray.path >/dev/null
  systemctl start hy2-aio-reload-hysteria.path || true
  systemctl start hy2-aio-reload-xray.path || true

  if ! systemctl restart hy2-aio.service; then
    journalctl -u hy2-aio.service --no-pager -n 100 >&2 || true
    die "HY2 AIO 后端升级失败"
  fi
  systemctl start hy2-aio-reload-hysteria.path || true
  systemctl start hy2-aio-reload-xray.path || true
  if hy2_has_enabled_user; then
    restart_hy2_xray_or_die
  else
    systemctl stop hy2-xray.service || true
  fi

  if ! systemctl reload caddy.service 2>/dev/null; then
    if ! systemctl restart caddy.service; then
      journalctl -u caddy.service --no-pager -n 80 >&2 || true
      die "Caddy 重载失败（hy2 已安装；修好 Caddy 后执行：hy2 repair）"
    fi
  fi

  sleep 2
  systemctl is-active --quiet hy2-aio.service || die "HY2 AIO 后端未运行"

  # is-active 通过只代表进程在，HTTP 端口可能还没开始监听（Python 起来要
  # 1~2 秒）。等端口通了再调 sync，否则会白打一行
  # "curl: (7) Failed to connect to 127.0.0.1 port 18081"，看着像失败。
  wait_backend_ready 10 || true
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
  if [ -n "${HY2_FETCH_MODULES_SHA:-}" ]; then
    if [ -n "${HY2_FETCH_COMMIT:-}" ]; then
      log "模块哈希：${HY2_FETCH_MODULES_SHA:0:12}（提交 ${HY2_FETCH_COMMIT:0:12}）"
    else
      log "模块哈希：${HY2_FETCH_MODULES_SHA:0:12}"
    fi
  fi
  log "已写入 QUIC 保活、混淆开关与 VLESS+Reality；Hysteria 未自动重启"
  log "使配置生效：hy2 restart（或 hy2 obfs on|off）"
  echo "运行速率模式菜单：hy2 mode"
  echo "查看面板账号：hy2 panel"
  print_welcome_banner
}

backup_cmd() {
  need_root backup
  read_env
  api_post backup
  echo
}
