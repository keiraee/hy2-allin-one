#!/usr/bin/env python3
import json
import os
import sys
import tempfile
from pathlib import Path

for _cand in (
    str(Path(__file__).resolve().parent) if "__file__" in globals() else "",
    "/usr/local/lib/hy2-aio",
    str(Path.cwd() / "app"),
):
    if _cand and _cand not in sys.path and (Path(_cand) / "common.py").is_file():
        sys.path.insert(0, _cand)

from common import (
    read_env_file as read_env,
    reality_dest,
    resolve_xray_port,
    user_is_disabled,
)

ENV_FILE = Path(os.environ.get("HY2_ENV_FILE", "/etc/hy2-aio/config.env"))
USERS_FILE = Path(os.environ.get("HY2_USERS_FILE", "/etc/hy2-aio/users.json"))
OUT_FILE = Path(os.environ.get("HY2_XRAY_CONFIG", "/etc/hy2-aio/xray.json"))


env = read_env(ENV_FILE)
users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
if not isinstance(users, dict) or not users:
    raise SystemExit("users.json 不能为空")

private_key = str(env.get("REALITY_PRIVATE_KEY") or "").strip()
if not private_key:
    raise SystemExit("缺少 REALITY_PRIVATE_KEY")
dest = reality_dest(env)
names_raw = str(env.get("REALITY_SERVER_NAMES") or "").strip()
server_names = [item.strip() for item in names_raw.split(",") if item.strip()]
if not server_names:
    server_names = [dest.rsplit(":", 1)[0]]
short_id = str(env.get("REALITY_SHORT_ID") or "").strip()
short_ids = [short_id] if short_id else [""]

clients = []
for username, info in sorted(users.items()):
    if not isinstance(info, dict):
        raise SystemExit(f"用户 {username} 格式错误")
    if user_is_disabled(info):
        continue
    vless_id = str(info.get("vless_id") or "").strip()
    if not vless_id:
        raise SystemExit(f"用户 {username} 缺少 vless_id")
    clients.append(
        {
            "id": vless_id,
            "email": username,
            "flow": "xtls-rprx-vision",
        }
    )
if not clients:
    print("所有用户已禁用：未写入任何 VLESS 账号", file=sys.stderr)

config = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "listen": "0.0.0.0",
            "port": resolve_xray_port(env),
            "protocol": "vless",
            "settings": {
                "clients": clients,
                "decryption": "none",
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "dest": dest,
                    "serverNames": server_names,
                    "privateKey": private_key,
                    "shortIds": short_ids,
                },
            },
            "sniffing": {
                "enabled": True,
                "destOverride": ["http", "tls"],
                "routeOnly": True,
            },
        }
    ],
    "outbounds": [{"protocol": "freedom", "tag": "direct"}],
}

descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{OUT_FILE.name}.", suffix=".tmp", dir=OUT_FILE.parent
)
temporary = Path(temporary_name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temporary, 0o640)
    os.replace(temporary, OUT_FILE)
finally:
    temporary.unlink(missing_ok=True)
os.chmod(OUT_FILE, 0o640)
try:
    import grp
    import pwd
    uid = pwd.getpwnam("hy2-aio").pw_uid
    gid = grp.getgrnam("hy2-aio").gr_gid
    try:
        os.chown(OUT_FILE, uid, gid)
    except PermissionError:
        os.chown(OUT_FILE, -1, gid)
except Exception:
    pass
