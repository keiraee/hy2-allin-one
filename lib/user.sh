#!/usr/bin/env bash
# user.sh - 用户管理

generate_users() {
  local count="$1"
  python3 - "$count" "$USERS_FILE" <<'PY'
import json, os, secrets, sys
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
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
  chmod 0640 "$USERS_FILE"
  chown hy2-aio:hy2-aio "$USERS_FILE"
}

modify_user() {
  local action="$1" username="${2:-}"
  need_root "$action"
  read_env
  valid_name "$username" || die "用户名仅允许字母、数字、下划线、短横线，长度 1-32"

  cp "$USERS_FILE" "${USERS_FILE}.bak"
  case "$action" in
    add-user)
      python3 - "$USERS_FILE" "$username" <<'PY'
import json, os, secrets, sys
path, username = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username in users:
    raise SystemExit("用户已存在")
users[username] = {
    "password": secrets.token_hex(16),
    "token": secrets.token_hex(24),
    "note": "",
    "disabled": False,
}
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    remove-user)
      python3 - "$USERS_FILE" "$username" <<'PY'
import json, os, sys
path, username = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username not in users:
    raise SystemExit("用户不存在")
if len(users) <= 1:
    raise SystemExit("不能删除最后一个用户")
del users[username]
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    rotate-user)
      python3 - "$USERS_FILE" "$username" <<'PY'
import json, os, secrets, sys
path, username = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username not in users:
    raise SystemExit("用户不存在")
users[username]["password"] = secrets.token_hex(16)
users[username]["token"] = secrets.token_hex(24)
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    note)
      python3 - "$USERS_FILE" "$username" "${3:-}" <<'PY'
import json, os, sys
path, username, note = sys.argv[1:]
if len(note) > 100:
    raise SystemExit("备注最长 100 字符")
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username not in users:
    raise SystemExit("用户不存在")
users[username]["note"] = note
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    disable|enable)
      python3 - "$USERS_FILE" "$username" "$action" <<'PY'
import json, os, sys
path, username, action = sys.argv[1:]
with open(path, "r", encoding="utf-8") as file:
    users = json.load(file)
if username not in users:
    raise SystemExit("用户不存在")
users[username]["disabled"] = action == "disable"
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as file:
    json.dump(users, file, ensure_ascii=False, indent=2)
os.replace(temporary, path)
PY
      ;;
    *) die "未知用户操作：$action" ;;
  esac

  chown hy2-aio:hy2-aio "$USERS_FILE"
  chmod 0640 "$USERS_FILE"
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG"
  chmod 0640 "$HYSTERIA_CONFIG"

  if ! systemctl restart hysteria-server.service; then
    warn "Hysteria 重启失败，恢复用户配置"
    mv "${USERS_FILE}.bak" "$USERS_FILE"
    "$REBUILD_FILE"
    systemctl restart hysteria-server.service || true
    die "修改失败"
  fi
  rm -f "${USERS_FILE}.bak"
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
