#!/usr/bin/env bash
# mode.sh - BBR/Brutal 速率模式管理

ensure_mode_file() {
  install -d -o root -g hy2-aio -m 0750 "$CONFIG_DIR"
  python3 - "$MODE_FILE" "$USERS_FILE" <<'PY'
import json
import os
import sys
from pathlib import Path

mode_path = Path(sys.argv[1])
users_path = Path(sys.argv[2])

try:
    users = json.loads(users_path.read_text(encoding="utf-8"))
except Exception:
    users = {}

try:
    raw = json.loads(mode_path.read_text(encoding="utf-8"))
except Exception:
    raw = {}

def normalize(value):
    if not isinstance(value, dict):
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    mode = str(value.get("mode", "bbr")).lower()
    if mode != "brutal":
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    if up <= 0 or down <= 0:
        return {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}
    return {"mode": "brutal", "up_mbps": up, "down_mbps": down}

# 兼容早期全局扁平格式：{"mode":"brutal", ...}
if isinstance(raw, dict) and "mode" in raw:
    data = {"default": normalize(raw), "users": {}}
else:
    default = normalize(raw.get("default", {}) if isinstance(raw, dict) else {})
    overrides = raw.get("users", {}) if isinstance(raw, dict) else {}
    clean = {}
    if isinstance(overrides, dict):
        for username, value in overrides.items():
            if username in users:
                clean[username] = normalize(value)
    data = {"default": default, "users": clean}

temporary = mode_path.with_suffix(mode_path.suffix + ".tmp")
temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temporary, mode_path)
PY
  chown hy2-aio:hy2-aio "$MODE_FILE"
  chmod 0640 "$MODE_FILE"
}

mode_show_plain() {
  python3 - "$MODE_FILE" "$USERS_FILE" <<'PY'
import json
import sys
from pathlib import Path

mode_path = Path(sys.argv[1])
users_path = Path(sys.argv[2])

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def normalize(value):
    if not isinstance(value, dict) or str(value.get("mode", "bbr")).lower() != "brutal":
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    if up <= 0 or down <= 0:
        return {"mode": "bbr", "up_mbps": 0.0, "down_mbps": 0.0}
    return {"mode": "brutal", "up_mbps": up, "down_mbps": down}

def label(value):
    item = normalize(value)
    if item["mode"] != "brutal":
        return "BBR 自动估速"
    return f'Brutal 上传 {item["up_mbps"]:g} / 下载 {item["down_mbps"]:g} Mbps'

data = load(mode_path, {})
users = load(users_path, {})
if isinstance(data, dict) and "mode" in data:
    data = {"default": normalize(data), "users": {}}
if not isinstance(data, dict):
    data = {}
default = normalize(data.get("default", {}))
overrides = data.get("users", {}) if isinstance(data.get("users", {}), dict) else {}

print(f"全局默认：{label(default)}")
print("用户实际模式：")
for username in sorted(users):
    if username in overrides:
        print(f"  {username}: {label(overrides[username])}（单独设置）")
    else:
        print(f"  {username}: {label(default)}（继承默认）")
PY
}

mode_apply() {
  local scope="$1" target="$2" mode="$3" up="${4:-0}" down="${5:-0}"
  local backup="${MODE_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  cp -a "$MODE_FILE" "$backup"

  if ! python3 - "$MODE_FILE" "$USERS_FILE" "$scope" "$target" "$mode" "$up" "$down" <<'PY'
import json
import os
import sys
from pathlib import Path

mode_path = Path(sys.argv[1])
users_path = Path(sys.argv[2])
scope = sys.argv[3]
target = sys.argv[4]
mode = sys.argv[5].lower()

try:
    users = json.loads(users_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit("users.json 读取失败")

try:
    data = json.loads(mode_path.read_text(encoding="utf-8"))
except Exception:
    data = {"default": {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}, "users": {}}

if isinstance(data, dict) and "mode" in data:
    data = {"default": data, "users": {}}
if not isinstance(data, dict):
    data = {}
data.setdefault("default", {"mode": "bbr", "up_mbps": 0, "down_mbps": 0})
data.setdefault("users", {})
if not isinstance(data["users"], dict):
    data["users"] = {}

if scope == "user" and target not in users:
    raise SystemExit(f"用户不存在：{target}")

if mode == "inherit":
    if scope != "user":
        raise SystemExit("只有单个用户可以恢复继承默认")
    data["users"].pop(target, None)
else:
    if mode == "brutal":
        try:
            up_value = float(sys.argv[6])
            down_value = float(sys.argv[7])
        except ValueError:
            raise SystemExit("上传和下载必须是数字")
        if up_value <= 0 or down_value <= 0:
            raise SystemExit("Brutal 上传和下载必须大于 0")
        if up_value > 2000 or down_value > 2000:
            raise SystemExit("单项最高允许 2000 Mbps")
        value = {"mode": "brutal", "up_mbps": up_value, "down_mbps": down_value}
    else:
        value = {"mode": "bbr", "up_mbps": 0, "down_mbps": 0}

    if scope == "default":
        data["default"] = value
    else:
        data["users"][target] = value

temporary = mode_path.with_suffix(mode_path.suffix + ".tmp")
temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temporary, mode_path)
PY
  then
    # Keep the pre-change copy so operators can recover after a write failure.
    die "速率模式写入失败（已保留备份：$backup）"
  fi

  chown hy2-aio:hy2-aio "$MODE_FILE"
  chmod 0640 "$MODE_FILE"

  if ! systemctl restart hy2-aio.service; then
    warn "订阅后端重启失败，恢复上一份模式配置"
    mv "$backup" "$MODE_FILE"
    chown hy2-aio:hy2-aio "$MODE_FILE"
    chmod 0640 "$MODE_FILE"
    systemctl restart hy2-aio.service || true
    die "模式切换失败"
  fi

  rm -f "$backup"
  sleep 2
  api_post sync >/dev/null || true
  write_access_file
  echo
  mode_show_plain
  echo
  echo "已更新 Clash 订阅；Hysteria 服务未重启。"
  echo "请在客户端刷新订阅并重新选择节点。"
}

mode_apply_preset() {
  local scope="$1" target="$2" preset="$3"
  case "$preset" in
    bbr|auto|1) mode_apply "$scope" "$target" bbr 0 0 ;;
    30|2) mode_apply "$scope" "$target" brutal 10 30 ;;
    50|3) mode_apply "$scope" "$target" brutal 15 50 ;;
    80|4) mode_apply "$scope" "$target" brutal 20 80 ;;
    120|5) mode_apply "$scope" "$target" brutal 30 120 ;;
    200|6) mode_apply "$scope" "$target" brutal 50 200 ;;
    300|7) mode_apply "$scope" "$target" brutal 80 300 ;;
    inherit|9) mode_apply "$scope" "$target" inherit 0 0 ;;
    *) return 1 ;;
  esac
}

mode_menu_presets() {
  local allow_inherit="${1:-0}"
  echo
  echo "1. BBR 自动估速"
  echo "2. Brutal 上传 10 / 下载 30 Mbps（下载理论 3.75 MB/s）"
  echo "3. Brutal 上传 15 / 下载 50 Mbps（下载理论 6.25 MB/s）"
  echo "4. Brutal 上传 20 / 下载 80 Mbps（下载理论 10 MB/s）"
  echo "5. Brutal 上传 30 / 下载 120 Mbps（下载理论 15 MB/s）"
  echo "6. Brutal 上传 50 / 下载 200 Mbps（下载理论 25 MB/s）"
  echo "7. Brutal 上传 80 / 下载 300 Mbps（下载理论 37.5 MB/s）"
  echo "8. 自定义 Mbps"
  [ "$allow_inherit" = "1" ] && echo "9. 恢复继承全局默认"
  echo "0. 退出"
}

mode_interactive() {
  echo "============================================================"
  echo "HY2 客户端速率模式"
  echo "============================================================"
  mode_show_plain
  echo
  echo "1. 修改全局默认（所有未单独设置的用户）"
  echo "2. 修改单个用户"
  echo "0. 退出"
  echo
  read -r -p "请选择目标：" target_choice

  local scope target allow_inherit=0
  case "$target_choice" in
    0) return 0 ;;
    1) scope="default"; target="default" ;;
    2)
      scope="user"
      allow_inherit=1
      echo "现有用户：$(python3 - "$USERS_FILE" <<'PY'
import json, sys
print(" ".join(sorted(json.load(open(sys.argv[1], encoding="utf-8")))))
PY
)"
      read -r -p "请输入用户名：" target
      valid_name "$target" || die "用户名格式错误"
      ;;
    *) die "输入无效" ;;
  esac

  mode_menu_presets "$allow_inherit"
  echo
  read -r -p "请输入数字：" preset
  [ "$preset" = "0" ] && return 0

  if [ "$preset" = "8" ]; then
    local up down
    read -r -p "上传目标 Mbps：" up
    read -r -p "下载目标 Mbps：" down
    mode_apply "$scope" "$target" brutal "$up" "$down"
    return
  fi

  mode_apply_preset "$scope" "$target" "$preset" || die "输入无效"
}

mode_cmd() {
  need_root mode
  read_env
  ensure_mode_file

  local target="${2:-}" preset="${3:-}"
  if [ -z "$target" ]; then
    mode_interactive
    return
  fi

  if [ "$target" = "show" ]; then
    mode_show_plain
    return
  fi

  local scope
  if [ "$target" = "default" ]; then
    scope="default"
  else
    scope="user"
    valid_name "$target" || die "用户名格式错误"
  fi

  [ -n "$preset" ] || die "缺少模式。示例：sudo hy2 mode $target 80"

  if [ "$preset" = "custom" ]; then
    [ "$#" -eq 5 ] || die "用法：sudo hy2 mode $target custom 上传Mbps 下载Mbps"
    mode_apply "$scope" "$target" brutal "$4" "$5"
    return
  fi

  mode_apply_preset "$scope" "$target" "$preset" || die "未知模式：$preset"
}
