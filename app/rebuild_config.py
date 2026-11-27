#!/usr/bin/env python3
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ENV_FILE = Path(os.environ.get("HY2_ENV_FILE", "/etc/hy2-aio/config.env"))
USERS_FILE = Path(os.environ.get("HY2_USERS_FILE", "/etc/hy2-aio/users.json"))
OUT_FILE = Path(os.environ.get("HY2_HYSTERIA_CONFIG", "/etc/hysteria/config.yaml"))

def read_env(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key] = value
    return values

def user_is_disabled(info: dict) -> bool:
    value = info.get("disabled", False)
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def user_password(info: dict, username: str) -> str:
    password = info.get("password")
    if password is None or str(password).strip() == "":
        raise SystemExit(f"用户 {username} 缺少 password")
    return str(password)


env = read_env(ENV_FILE)
users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
if not isinstance(users, dict) or not users:
    raise SystemExit("users.json 不能为空")

userpass_lines = []
for username, info in sorted(users.items()):
    if not isinstance(info, dict):
        raise SystemExit(f"用户 {username} 格式错误")
    if user_is_disabled(info):
        continue
    userpass_lines.append(
        f"    {json.dumps(username)}: {json.dumps(user_password(info, username))}"
    )
if not userpass_lines:
    print("所有用户已禁用：未写入任何认证账号", file=sys.stderr)

def truthy(key: str, default: str = "false") -> bool:
    return str(env.get(key, default)).strip().lower() in ("1", "true", "yes", "on")

# 端口跳跃：listen 写范围时，Hysteria 自己用 nft/iptables 把范围内其他端口
# 重定向到第一个端口；范围写坏会让 Hysteria 拒绝启动，所以这里先校验再落盘。
hop_enabled = truthy("PORT_HOP_ENABLED", "false")
base_port = str(env.get("HY2_PORT", "443")).strip()
listen_port = base_port
if hop_enabled:
    hop_range = str(env.get("PORT_HOP_RANGE") or "").strip()
    try:
        base_number = int(base_port)
    except ValueError:
        raise SystemExit(f"HY2_PORT 不是有效端口：{base_port}")
    if not hop_range:
        hop_range = f"{base_number}-{min(base_number + 1000, 65535)}"
    match = re.fullmatch(r"([0-9]{1,5})-([0-9]{1,5})", hop_range)
    if not match:
        raise SystemExit(f"PORT_HOP_RANGE 格式错误：{hop_range}（应形如 {base_number}-{base_number + 1000}）")
    start, end = int(match.group(1)), int(match.group(2))
    if start != base_number or end <= start or end > 65535 or end - start > 2000:
        raise SystemExit(
            f"PORT_HOP_RANGE 无效：{hop_range}（须从 HY2_PORT={base_number} 开始、跨度 ≤2000）"
        )
    listen_port = f"{start}-{end}"

lines = [
    f'listen: ":{listen_port}"',
    "",
    "quic:",
    f'  maxIdleTimeout: {json.dumps(env.get("QUIC_MAX_IDLE_TIMEOUT", "120s"))}',
    f'  keepAlivePeriod: {json.dumps(env.get("QUIC_KEEP_ALIVE_PERIOD", "5s"))}',
    "",
    "tls:",
    '  cert: "/etc/hysteria/server.crt"',
    '  key: "/etc/hysteria/server.key"',
    f"  sniGuard: {json.dumps(env.get('SNI_GUARD', 'disable'))}",
    "",
    "auth:",
    "  type: userpass",
]
if userpass_lines:
    lines.append("  userpass:")
    lines.extend(userpass_lines)
else:
    lines.append("  userpass: {}")

speed_test = truthy("SPEED_TEST", "false")
obfs_enabled = truthy("OBFS_ENABLED", "true")
lines.append("")
if obfs_enabled:
    lines.extend([
        "obfs:",
        "  type: salamander",
        "  salamander:",
        f"    password: {json.dumps(env['OBFS_PASSWORD'])}",
        "",
    ])
lines.extend([
    "congestion:",
    "  type: bbr",
    "  bbrProfile: standard",
    "",
    f"speedTest: {'true' if speed_test else 'false'}",
    "disableUDP: false",
    "",
    "trafficStats:",
    f'  listen: "127.0.0.1:{env.get("STATS_PORT", "9999")}"',
    f"  secret: {json.dumps(env['API_SECRET'])}",
    "",
    "sniff:",
    "  enable: true",
    "  timeout: 2s",
    "  tcpPorts: 80,443",
    "  udpPorts: 443",
    "",
])

descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{OUT_FILE.name}.", suffix=".tmp", dir=OUT_FILE.parent
)
temporary = Path(temporary_name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temporary, 0o660)
    os.replace(temporary, OUT_FILE)
finally:
    temporary.unlink(missing_ok=True)
os.chmod(OUT_FILE, 0o660)
# hy2-aio may rewrite this file; ensure hysteria can still read it.
try:
    import grp
    import pwd
    uid = pwd.getpwnam("hysteria").pw_uid
    gid = grp.getgrnam("hysteria").gr_gid
    try:
        os.chown(OUT_FILE, uid, gid)
    except PermissionError:
        # Non-root: keep current owner, set group to hysteria (hy2-aio is in that group).
        os.chown(OUT_FILE, -1, gid)
except Exception:
    pass
