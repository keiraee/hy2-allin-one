#!/usr/bin/env bash
# access.sh - 访问资料文件生成

write_access_file() {
  read_env
  python3 - "$ENV_FILE" "$USERS_FILE" "$MODE_FILE" "$ACCESS_FILE" <<'PY'
import json, pathlib, sys, urllib.parse

env_file, users_file, mode_file, out_file = map(pathlib.Path, sys.argv[1:])
env = {}
for raw in env_file.read_text(encoding="utf-8").splitlines():
    raw = raw.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        env[key] = value

users = json.loads(users_file.read_text(encoding="utf-8"))
try:
    modes = json.loads(mode_file.read_text(encoding="utf-8"))
except Exception:
    modes = {"default": {"mode": "bbr"}, "users": {}}
if isinstance(modes, dict) and "mode" in modes:
    modes = {"default": modes, "users": {}}
if not isinstance(modes, dict):
    modes = {}
default_mode = modes.get("default", {"mode": "bbr"})
overrides = modes.get("users", {}) if isinstance(modes.get("users", {}), dict) else {}

def mode_label(value):
    if not isinstance(value, dict) or str(value.get("mode", "bbr")).lower() != "brutal":
        return "BBR 自动估速"
    try:
        up = float(value.get("up_mbps", 0))
        down = float(value.get("down_mbps", 0))
    except (TypeError, ValueError):
        return "BBR 自动估速"
    if up <= 0 or down <= 0:
        return "BBR 自动估速"
    return f"Brutal 上传 {up:g} / 下载 {down:g} Mbps"

def public_base_url():
    domain = env["DOMAIN"]
    port = str(env.get("PANEL_PORT", "443") or "443")
    if port in ("443", ""):
        return f"https://{domain}"
    return f"https://{domain}:{port}"

base = public_base_url()
obfs_raw = str(env.get("OBFS_ENABLED", "true")).strip().lower()
obfs_label = "salamander（开）" if obfs_raw in ("1", "true", "yes", "on") else "关"
lines = [
    "HY2 AIO 访问资料",
    "=" * 64,
    f"版本：{env.get('AIO_VERSION', '')}",
    f"服务器：{env['PUBLIC_IP']}",
    f"端口：{env.get('HY2_PORT', '443')}/UDP",
    f"混淆：{obfs_label}",
    f"面板：{base}/{env['PANEL_PATH']}/",
    f"面板用户名：{env['PANEL_USER']}",
    f"面板密码：{env['PANEL_PASS']}",
    f"套餐总量（字节）：{env['TOTAL_BYTES']}",
    "",
]

for username, info in sorted(users.items()):
    password = str(info["password"])
    token = str(info["token"])
    subscription = f"{base}/s/{token}"
    auth = urllib.parse.quote(f"{username}:{password}", safe="")
    query_items = {
        "sni": env.get("SNI", "www.amazon.sg"),
    }
    obfs_raw = str(env.get("OBFS_ENABLED", "true")).strip().lower()
    if obfs_raw in ("1", "true", "yes", "on"):
        query_items["obfs"] = "salamander"
        query_items["obfs-password"] = env["OBFS_PASSWORD"]
    insecure_raw = str(env.get("CLIENT_INSECURE", "")).strip().lower()
    if insecure_raw in ("0", "false", "no", "off"):
        insecure = False
    elif insecure_raw in ("1", "true", "yes", "on"):
        insecure = True
    else:
        domain = str(env.get("DOMAIN", ""))
        insecure = domain.endswith("sslip.io") or domain == str(env.get("PUBLIC_IP", ""))
    if insecure:
        query_items["insecure"] = "1"
    query = urllib.parse.urlencode(query_items)
    node = urllib.parse.quote(f"HY2-{username}", safe="")
    direct = f"hysteria2://{auth}@{env['PUBLIC_IP']}:{env.get('HY2_PORT', '443')}/?{query}#{node}"
    lines.extend(
        [
            f"【{username}】",
            f"用户名：{username}",
            f"状态：{'已禁用' if info.get('disabled') else '正常'}",
            f"设备备注：{info.get('note', '') or '（无）'}",
            f"密码：{password}",
            f"速率模式：{mode_label(overrides.get(username, default_mode))}",
            f"Clash 订阅：{subscription}",
            f"HY2 基础直链（不含速率模式）：{direct}",
            "",
        ]
    )

out_file.write_text("\n".join(lines), encoding="utf-8")
PY
  chmod 0600 "$ACCESS_FILE"

  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    local user_home
    user_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    if [ -n "$user_home" ] && [ -d "$user_home" ]; then
      cp "$ACCESS_FILE" "$user_home/hy2-aio-access.txt"
      chown "$SUDO_USER":"$SUDO_USER" "$user_home/hy2-aio-access.txt" 2>/dev/null || true
      chmod 0600 "$user_home/hy2-aio-access.txt"
    fi
  fi
}
