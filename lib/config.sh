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
    f"  sniGuard: {json.dumps(env.get('SNI_GUARD', 'disable'))}",
    "",
    "auth:",
    "  type: userpass",
    "  userpass:",
]
for username, info in sorted(users.items()):
    if info.get("disabled"):
        continue
    lines.append(f"    {json.dumps(username)}: {json.dumps(str(info['password']))}")

speed_test = str(env.get("SPEED_TEST", "false")).strip().lower() in ("1", "true", "yes", "on")
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
    f"speedTest: {'true' if speed_test else 'false'}",
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
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
LockPersonality=true
SystemCallArchitectures=native
ReadWritePaths=/etc/hy2-aio /var/lib/hy2-aio /var/www/hy2-aio /etc/hysteria
ReadOnlyPaths=/usr/local/lib/hy2-aio

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
  local hash auth site_file marker
  hash="$(caddy hash-password --plaintext "$PANEL_PASS")"
  auth="$(caddy_auth_directive)"
  site_file="/etc/caddy/hy2-aio.caddy"
  marker="import ${site_file}"
  install -d -m 0755 /etc/caddy

  if [ -f "$CADDY_FILE" ]; then
    cp "$CADDY_FILE" "${CADDY_FILE}.before-hy2-aio-$(date +%Y%m%d-%H%M%S)"
  fi

  cat > "$site_file" <<EOF
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
            reverse_proxy 127.0.0.1:18081 {
                header_up X-API-Secret ${API_SECRET}
            }
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
                Content-Security-Policy "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
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

  if [ ! -f "$CADDY_FILE" ]; then
    cat > "$CADDY_FILE" <<EOF
{
    servers {
        protocols h1 h2
    }
}

${marker}
EOF
  elif grep -Fq "$marker" "$CADDY_FILE"; then
    :
  elif grep -Eq "^${DOMAIN}(:${PANEL_PORT})?[[:space:]]*\\{" "$CADDY_FILE" \
    || grep -Fq "root * ${WEB_DIR}" "$CADDY_FILE"; then
    # Replace legacy full-file HY2 Caddyfile with import-based layout.
    cat > "$CADDY_FILE" <<EOF
{
    servers {
        protocols h1 h2
    }
}

${marker}
EOF
  else
    # Preserve unrelated site configs; only append our import.
    printf '\n%s\n' "$marker" >> "$CADDY_FILE"
  fi

  caddy fmt --overwrite "$site_file"
  caddy fmt --overwrite "$CADDY_FILE"
  caddy validate --config "$CADDY_FILE"
}
