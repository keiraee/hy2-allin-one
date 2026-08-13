#!/usr/bin/env bash
# user.sh - 用户管理

generate_users() {
  local count="$1"
  python3 - "$count" "$USERS_FILE" <<'PY'
import json, os, secrets, sys, tempfile
count = int(sys.argv[1])
path = sys.argv[2]
users = {}
for index in range(1, count + 1):
    users[f"user{index}"] = {
        "password": secrets.token_hex(16),
        "token": secrets.token_hex(24),
        "note": "",
        "disabled": False,
    }
descriptor, temporary = tempfile.mkstemp(prefix=".users.json.", suffix=".tmp", dir=os.path.dirname(path))
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(users, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
  chmod 0640 "$USERS_FILE"
  chown hy2-aio:hy2-aio "$USERS_FILE"
}

mutate_user_json() {
  local action="$1" username="$2" value="${3:-}"
  python3 - "$USERS_FILE" "$action" "$username" "$value" <<'PY'
import json, os, secrets, sys, tempfile

path, action, username, value = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)

if action == "add-user":
    if username in users:
        raise SystemExit("用户已存在")
    users[username] = {
        "password": secrets.token_hex(16),
        "token": secrets.token_hex(24),
        "note": "",
        "disabled": False,
    }
elif action == "remove-user":
    if username not in users:
        raise SystemExit("用户不存在")
    if len(users) <= 1:
        raise SystemExit("不能删除最后一个用户")
    del users[username]
elif action == "rotate-user":
    if username not in users:
        raise SystemExit("用户不存在")
    users[username]["password"] = secrets.token_hex(16)
    users[username]["token"] = secrets.token_hex(24)
elif action == "note":
    if len(value) > 100:
        raise SystemExit("备注最长 100 字符")
    if username not in users:
        raise SystemExit("用户不存在")
    users[username]["note"] = value
elif action in ("disable", "enable"):
    if username not in users:
        raise SystemExit("用户不存在")
    users[username]["disabled"] = action == "disable"
else:
    raise SystemExit(f"未知用户操作：{action}")

directory = os.path.dirname(path)
descriptor, temporary = tempfile.mkstemp(prefix=".users.json.", suffix=".tmp", dir=directory)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(users, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
}

forget_deleted_user_files() {
  local username="$1"
  python3 - "$MODE_FILE" "${STATE_DIR}/state.json" "$username" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

mode_path = Path(sys.argv[1])
state_path = Path(sys.argv[2])
username = sys.argv[3]


def atomic_write(path: Path, data) -> None:
    directory = str(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


if mode_path.is_file():
    try:
        modes = json.loads(mode_path.read_text(encoding="utf-8"))
    except Exception:
        modes = {}
    if isinstance(modes, dict) and isinstance(modes.get("users"), dict) and username in modes["users"]:
        modes["users"].pop(username, None)
        atomic_write(mode_path, modes)

if state_path.is_file():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    users_state = state.get("users") if isinstance(state, dict) else None
    if isinstance(users_state, dict) and username in users_state:
        users_state.pop(username, None)
        atomic_write(state_path, state)
PY
  chown hy2-aio:hy2-aio "$MODE_FILE" 2>/dev/null || true
  chmod 0640 "$MODE_FILE" 2>/dev/null || true
}

modify_user() {
  local action="$1" username="${2:-}"
  local value="${3:-}" user_lock_fd users_backup config_backup failure=""
  need_root "$action"
  read_env
  valid_name "$username" || die "用户名仅允许字母、数字、下划线、短横线，长度 1-32"

  touch "$USER_MUTATION_LOCK"
  chown hy2-aio:hy2-aio "$USER_MUTATION_LOCK"
  chmod 0660 "$USER_MUTATION_LOCK"
  exec {user_lock_fd}>"$USER_MUTATION_LOCK"
  flock -x "$user_lock_fd"

  users_backup="$(mktemp "${CONFIG_DIR}/.users.json.rollback.XXXXXX")"
  config_backup="$(mktemp "${HYSTERIA_DIR}/.config.yaml.rollback.XXXXXX")"
  cp -a "$USERS_FILE" "$users_backup"
  cp -a "$HYSTERIA_CONFIG" "$config_backup"

  if ! mutate_user_json "$action" "$username" "$value"; then
    failure="用户数据修改失败"
  elif ! chown hy2-aio:hy2-aio "$USERS_FILE" || ! chmod 0640 "$USERS_FILE"; then
    failure="用户文件权限设置失败"
  elif ! "$REBUILD_FILE"; then
    failure="Hysteria 配置重建失败"
  elif ! chown hysteria:hysteria "$HYSTERIA_CONFIG" || ! chmod 0660 "$HYSTERIA_CONFIG"; then
    failure="Hysteria 配置权限设置失败"
  elif ! systemctl restart hysteria-server.service; then
    failure="Hysteria 重启失败"
  fi

  if [ -n "$failure" ]; then
    warn "${failure}，恢复修改前状态"
    mv -f "$users_backup" "$USERS_FILE"
    mv -f "$config_backup" "$HYSTERIA_CONFIG"
    systemctl restart hysteria-server.service || true
    flock -u "$user_lock_fd"
    exec {user_lock_fd}>&-
    die "修改失败：$failure"
  fi

  rm -f "$users_backup" "$config_backup"
  flock -u "$user_lock_fd"
  exec {user_lock_fd}>&-
  if [ "$action" = "remove-user" ]; then
    forget_deleted_user_files "$username"
  fi
  systemctl restart hy2-aio.service
  sleep 2
  api_post sync >/dev/null || true
  write_access_file
  log "用户操作完成：$action $username"
  show_cmd
}

users_cmd() {
  need_root users
  read_env
  python3 - "$USERS_FILE" "$STATE_DIR/state.json" <<'PY'
import json, sys
users = json.load(open(sys.argv[1], encoding="utf-8"))
try:
    state = json.load(open(sys.argv[2], encoding="utf-8"))
except Exception:
    state = {}
stats = state.get("users", {})
print(f"{'用户':<18} {'月流量(MB)':>14} {'历史累计(MB)':>16}")
print("-" * 52)
for name in sorted(users):
    item = stats.get(name, {})
    month = int(item.get("month_tx", 0)) + int(item.get("month_rx", 0))
    total = int(item.get("lifetime_tx", 0)) + int(item.get("lifetime_rx", 0))
    print(f"{name:<18} {month/1_000_000:>14.2f} {total/1_000_000:>16.2f}")
PY
}
