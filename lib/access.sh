#!/usr/bin/env bash
# access.sh - 访问资料文件生成

write_access_file() {
  read_env
  python3 - "$ENV_FILE" "$USERS_FILE" "$MODE_FILE" "$ACCESS_FILE" "${WEB_DIR}/data.json" <<'PY'
import json, pathlib, sys, urllib.parse

for _cand in (
    "/usr/local/lib/hy2-aio",
    "/usr/local/lib/hy2-aio/modules/app",
    str(pathlib.Path.cwd() / "app"),
):
    if _cand and _cand not in sys.path and (pathlib.Path(_cand) / "common.py").is_file():
        sys.path.insert(0, _cand)

from common import (
    client_insecure,
    country_code_to_flag,
    obfs_enabled,
    port_hop_ports,
    public_base_url,
    read_env_file,
    reality_server_name,
    subscription_sni,
    user_is_disabled as is_disabled,
    xray_port as resolve_xray_port_str,
)

env_file, users_file, mode_file, out_file, data_file = map(pathlib.Path, sys.argv[1:])
env = read_env_file(env_file)
users = json.loads(users_file.read_text(encoding="utf-8"))


def node_flag() -> str:
    # 节点名的国旗必须和面板/订阅里的一模一样（面板走 backend 的 direct_links）。
    # 后端把解析好的归属地写在 data.json 的 server.country_code 上，这里只读结果：
    # hy2 show 是高频命令，不能为个国旗让它自己去挨 3×5 秒的网络超时。
    code = str(env.get("COUNTRY_CODE") or "").strip().upper()
    if not code:
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
            code = str(data["server"]["country_code"] or "")
        except Exception:
            code = ""
    flag = country_code_to_flag(code)
    return flag + " " if flag else ""


FLAG = node_flag()
HOP_PORTS = port_hop_ports(env)
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

base = public_base_url(env)
obfs_label = "salamander（开）" if obfs_enabled(env) else "关"
lines = [
    "HY2 AIO 访问资料",
    "=" * 64,
    f"版本：{env.get('AIO_VERSION', '')}",
    f"服务器：{env['PUBLIC_IP']}",
    f"HY2 端口：{HOP_PORTS or env.get('HY2_PORT', '443')}/UDP" + ("（端口跳跃）" if HOP_PORTS else ""),
    f"VLESS 端口：{resolve_xray_port_str(env)}/TCP",
    f"混淆：{obfs_label}",
    f"面板：{base}/{env['PANEL_PATH']}/",
    f"面板用户名：{env['PANEL_USER']}",
    f"面板密码：{env['PANEL_PASS']}",
    f"套餐总量：{'无限流量' if env.get('TOTAL_BYTES') == '0' else str(env.get('TOTAL_BYTES', '')) + ' 字节'}",
    "",
]

for username, info in sorted(users.items()):
    password = str(info["password"])
    token = str(info["token"])
    subscription = f"{base}/s/{token}"
    # 冒号是 userinfo 的分隔符，不能编码（同上，见 server.py 的说明）
    auth = (
        urllib.parse.quote(str(username), safe="")
        + ":"
        + urllib.parse.quote(str(password), safe="")
    )
    query_items = {"sni": subscription_sni(env)}
    if obfs_enabled(env):
        query_items["obfs"] = "salamander"
        query_items["obfs-password"] = env["OBFS_PASSWORD"]
    if client_insecure(env):
        query_items["insecure"] = "1"
    node = urllib.parse.quote(f"{FLAG}HY2-{username}", safe="")
    # 端口范围不能塞进 host:port（"8443-9443" 不是合法 URI 端口，
    # v2rayN/CMA 解析后 Address/Port 会双双落空）。范围走 mport。
    if HOP_PORTS:
        query_items["mport"] = HOP_PORTS
        hy2_port = HOP_PORTS.split("-", 1)[0]
    else:
        hy2_port = env.get("HY2_PORT", "443")
    query = urllib.parse.urlencode(query_items)
    direct = f"hysteria2://{auth}@{env['PUBLIC_IP']}:{hy2_port}/?{query}#{node}"
    xray_port_val = resolve_xray_port_str(env)
    vless_id = str(info.get("vless_id") or "").strip()
    public_key = str(env.get("REALITY_PUBLIC_KEY") or "").strip()
    short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
    server_name = reality_server_name(env)
    vless = ""
    if vless_id and public_key and short_id:
        vless_query = urllib.parse.urlencode(
            {
                "encryption": "none",
                "flow": "xtls-rprx-vision",
                "security": "reality",
                "sni": server_name,
                "fp": "chrome",
                "pbk": public_key,
                "sid": short_id,
                "type": "tcp",
            }
        )
        vless_name = urllib.parse.quote(f"{FLAG}hy2超时备用临时节点", safe="")
        vless = f"vless://{vless_id}@{env['PUBLIC_IP']}:{xray_port_val}?{vless_query}#{vless_name}"
    access_lines = [
        f"【{username}】",
        f"用户名：{username}",
        f"状态：{'已禁用' if is_disabled(info) else '正常'}",
        f"设备备注：{info.get('note', '') or '（无）'}",
        f"密码：{password}",
        f"速率模式：{mode_label(overrides.get(username, default_mode))}",
        "",
        "【订阅 · 按客户端选一个】",
        f"  Clash / mihomo  →  {subscription}",
        f"  v2ray 系        →  {subscription}?fmt=v2ray",
        f"  sing-box        →  {subscription}?fmt=singbox",
        "",
        "【直链 · 手动配置用】",
        f"  HY2：{direct}",
    ]
    if vless:
        access_lines.append(f"  VLESS：{vless}")
    access_lines.append("")
    lines.extend(access_lines)

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
