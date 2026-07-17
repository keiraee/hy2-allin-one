#!/usr/bin/env bash
# config.sh - Hysteria/Caddy/systemd 配置生成

write_rebuild_helper() {
  install -d -m 0755 "$APP_DIR"
  cat > "$REBUILD_FILE" <<'PY'
#!/usr/bin/env python3
import json
import os
from pathlib import Path

ENV_FILE = Path("/etc/hy2-aio/config.env")
USERS_FILE = Path("/etc/hy2-aio/users.json")
MODE_FILE = Path("/etc/hy2-aio/client-mode.json")
OUT_FILE = Path("/etc/hysteria/config.yaml")

def read_env(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key] = value
    return values

env = read_env(ENV_FILE)
users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
if not users:
    raise SystemExit("users.json 不能为空")

lines = [
    f'listen: ":{env.get("HY2_PORT", "443")}"',
    "",
    "tls:",
    '  cert: "/etc/hysteria/server.crt"',
    '  key: "/etc/hysteria/server.key"',
    "  sniGuard: disable",
    "",
    "auth:",
    "  type: userpass",
    "  userpass:",
]
for username, info in sorted(users.items()):
    lines.append(f"    {json.dumps(username)}: {json.dumps(str(info['password']))}")

lines.extend([
    "",
    "obfs:",
    "  type: salamander",
    "  salamander:",
    f"    password: {json.dumps(env['OBFS_PASSWORD'])}",
    "",
    "congestion:",
    "  type: bbr",
    "  bbrProfile: standard",
    "",
    "speedTest: true",
    "disableUDP: false",
    "",
    "trafficStats:",
    f'  listen: "127.0.0.1:{env.get("STATS_PORT", "9999")}"',
    f"  secret: {json.dumps(env['API_SECRET'])}",
    "",
])

temporary = OUT_FILE.with_suffix(".tmp")
temporary.write_text("\n".join(lines), encoding="utf-8")
os.replace(temporary, OUT_FILE)
PY
  chmod 0755 "$REBUILD_FILE"
}

write_systemd() {
  cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=HY2 AIO subscription, statistics and dashboard backend
After=network-online.target hysteria-server.service
Wants=network-online.target
Requires=hysteria-server.service

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/bin/python3 /usr/local/lib/hy2-aio/server.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=false

[Install]
WantedBy=multi-user.target
EOF
}

caddy_auth_directive() {
  local version major minor
  version="$(caddy version 2>/dev/null | sed -E 's/^v?([0-9]+)\.([0-9]+).*/\1 \2/' || true)"
  major="$(awk '{print $1}' <<<"$version")"
  minor="$(awk '{print $2}' <<<"$version")"
  if [ "${major:-2}" -gt 2 ] || { [ "${major:-2}" -eq 2 ] && [ "${minor:-6}" -ge 8 ]; }; then
    echo basic_auth
  else
    echo basicauth
  fi
}

write_caddy() {
  local hash auth
  hash="$(caddy hash-password --plaintext "$PANEL_PASS")"
  auth="$(caddy_auth_directive)"
  [ ! -f "$CADDY_FILE" ] || cp "$CADDY_FILE" "${CADDY_FILE}.before-hy2-aio-$(date +%Y%m%d-%H%M%S)"

  cat > "$CADDY_FILE" <<EOF
{
    servers {
        protocols h1 h2
    }
}

${DOMAIN}:${PANEL_PORT} {
    encode zstd gzip

    route {
        redir /${PANEL_PATH} /${PANEL_PATH}/ 308

        handle_path /${PANEL_PATH}/api/* {
            ${auth} {
                ${PANEL_USER} ${hash}
            }
            header {
                Cache-Control "no-store"
                X-Content-Type-Options "nosniff"
                X-Frame-Options "DENY"
                Referrer-Policy "no-referrer"
            }
            reverse_proxy 127.0.0.1:18081
        }

        handle_path /${PANEL_PATH}/* {
            ${auth} {
                ${PANEL_USER} ${hash}
            }
            header {
                Cache-Control "no-store, no-cache, must-revalidate"
                X-Content-Type-Options "nosniff"
                X-Frame-Options "DENY"
                Referrer-Policy "no-referrer"
            }
            root * ${WEB_DIR}
            file_server
        }

        handle /s/* {
            reverse_proxy 127.0.0.1:18081
        }

        handle {
            respond "Not Found" 404
        }
    }
}
EOF
  caddy fmt --overwrite "$CADDY_FILE"
  caddy validate --config "$CADDY_FILE"
}
