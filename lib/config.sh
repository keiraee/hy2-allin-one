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
os.chmod(OUT_FILE, 0o660)
try:
    import grp
    import pwd
    os.chown(OUT_FILE, pwd.getpwnam("hysteria").pw_uid, grp.getgrnam("hysteria").gr_gid)
except Exception:
    pass
PY
  chmod 0755 "$REBUILD_FILE"
}

write_systemd() {
  cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=HY2 AIO subscription, statistics and dashboard backend
After=network-online.target hysteria-server.service
Wants=network-online.target hysteria-server.service
# Do NOT Requires=hysteria-server — user mutations restart Hysteria and would
# otherwise tear down this backend mid-request (Caddy HTTP 502).

[Service]
Type=simple
User=hy2-aio
Group=hy2-aio
SupplementaryGroups=hysteria caddy
ExecStart=/usr/bin/python3 /usr/local/lib/hy2-aio/server.py
Restart=always
RestartSec=3
RuntimeDirectory=hy2-aio
RuntimeDirectoryMode=0750
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
ReadWritePaths=/etc/hy2-aio /var/lib/hy2-aio /var/www/hy2-aio /etc/hysteria /run/hy2-aio
ReadOnlyPaths=/usr/local/lib/hy2-aio

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/hy2-aio-reload-hysteria.path <<'EOF'
[Unit]
Description=Watch HY2 AIO request to reload Hysteria

[Path]
PathExists=/run/hy2-aio/reload-hysteria
Unit=hy2-aio-reload-hysteria.service

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/hy2-aio-reload-hysteria.service <<'EOF'
[Unit]
Description=Restart hysteria-server for HY2 AIO
After=hysteria-server.service

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart hysteria-server.service
ExecStartPost=/bin/rm -f /run/hy2-aio/reload-hysteria
EOF
}

ensure_hy2_aio_user() {
  getent group hy2-aio >/dev/null 2>&1 || groupadd --system hy2-aio
  getent group hysteria >/dev/null 2>&1 || groupadd --system hysteria
  getent group caddy >/dev/null 2>&1 || groupadd --system caddy
  if ! id hy2-aio >/dev/null 2>&1; then
    useradd --system --gid hy2-aio --groups hysteria,caddy \
      --home-dir "$STATE_DIR" --shell /usr/sbin/nologin hy2-aio
  else
    usermod -a -G hysteria,caddy hy2-aio 2>/dev/null || true
  fi
  install -d -o hy2-aio -g hy2-aio -m 0750 "$STATE_DIR" "$STATE_DIR/backups"
  install -d -o hy2-aio -g caddy -m 2750 "$WEB_DIR" "$WEB_DIR/downloads"
  # Group-writable so unprivileged backend can update users.json / mode atomically.
  install -d -o root -g hy2-aio -m 0770 "$CONFIG_DIR"
  install -d -o hysteria -g hysteria -m 0770 /etc/hysteria
  chown root:hy2-aio "$CONFIG_DIR" 2>/dev/null || true
  chmod 0770 "$CONFIG_DIR" 2>/dev/null || true
  chown hysteria:hysteria /etc/hysteria 2>/dev/null || true
  chmod 0770 /etc/hysteria 2>/dev/null || true
  # Allow hy2-aio (in hysteria group) to rewrite config.yaml via rebuild helper.
  if [ -f /etc/hysteria/config.yaml ]; then
    chown hysteria:hysteria /etc/hysteria/config.yaml
    chmod 0660 /etc/hysteria/config.yaml
  fi
  chown hy2-aio:hy2-aio "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  chmod 0640 "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
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
  local auth site_file marker
  auth="$(caddy_auth_directive)"
  site_file="/etc/caddy/hy2-aio.caddy"
  marker="import ${site_file}"
  install -d -m 0755 /etc/caddy
  install -d -o caddy -g caddy -m 0750 /var/log/caddy
  # Ensure Caddy can write site access logs (restart fails if root-owned).
  chown -R caddy:caddy /var/log/caddy 2>/dev/null || true
  touch /var/log/caddy/hy2-aio.log
  chown caddy:caddy /var/log/caddy/hy2-aio.log
  chmod 0640 /var/log/caddy/hy2-aio.log

  if [ -f "$CADDY_FILE" ]; then
    cp "$CADDY_FILE" "${CADDY_FILE}.before-hy2-aio-$(date +%Y%m%d-%H%M%S)"
  fi

  DOMAIN="$DOMAIN" PANEL_PORT="$PANEL_PORT" PANEL_PATH="$PANEL_PATH" \
    PANEL_USER="$PANEL_USER" PANEL_PASS="$PANEL_PASS" API_SECRET="$API_SECRET" \
    WEB_DIR="$WEB_DIR" AUTH_DIRECTIVE="$auth" SITE_FILE="$site_file" \
    python3 <<'PY'
import os
import subprocess
from pathlib import Path

domain = os.environ["DOMAIN"]
port = os.environ["PANEL_PORT"]
panel_path = os.environ["PANEL_PATH"]
panel_user = os.environ["PANEL_USER"]
panel_pass = os.environ["PANEL_PASS"]
api_secret = os.environ["API_SECRET"]
web_dir = os.environ["WEB_DIR"]
auth = os.environ["AUTH_DIRECTIVE"]
site_file = Path(os.environ["SITE_FILE"])

password_hash = subprocess.check_output(
    ["caddy", "hash-password", "--plaintext", panel_pass],
    text=True,
).strip()

port = str(port or "443")
if port == "80":
    # Explicit HTTP only on port 80.
    site_addr = f"http://{domain}"
elif port == "443":
    site_addr = domain
else:
    # Custom panel port: enable Caddy auto HTTPS (same as pre-v1.3.4 behavior).
    site_addr = f"{domain}:{port}"

content = f"""{site_addr} {{
    encode zstd gzip

    log {{
        output file /var/log/caddy/hy2-aio.log {{
            roll_size 10mb
            roll_keep 3
        }}
    }}

    route {{
        redir /{panel_path} /{panel_path}/ 308

        handle_path /{panel_path}/api/* {{
            {auth} {{
                {panel_user} {password_hash}
            }}
            header {{
                Cache-Control "no-store"
                X-Content-Type-Options "nosniff"
                X-Frame-Options "DENY"
                Referrer-Policy "no-referrer"
            }}
            reverse_proxy 127.0.0.1:18081 {{
                header_up X-API-Secret "{api_secret}"
                header_up X-Forwarded-For {{remote_host}}
                header_up X-Real-IP {{remote_host}}
            }}
        }}

        handle_path /{panel_path}/* {{
            {auth} {{
                {panel_user} {password_hash}
            }}
            header {{
                Cache-Control "no-store, no-cache, must-revalidate"
                X-Content-Type-Options "nosniff"
                X-Frame-Options "DENY"
                Referrer-Policy "no-referrer"
                Content-Security-Policy "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            }}
            root * {web_dir}
            file_server
        }}

        handle /s/* {{
            reverse_proxy 127.0.0.1:18081 {{
                header_up X-Forwarded-For {{remote_host}}
                header_up X-Real-IP {{remote_host}}
            }}
        }}

        handle {{
            respond "Not Found" 404
        }}
    }}
}}
"""
site_file.write_text(content, encoding="utf-8")
PY
  [ -f "$site_file" ] || die "写入 ${site_file} 失败"

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
  elif grep -Fq "$WEB_DIR" "$CADDY_FILE" \
    || grep -Eq "^${DOMAIN}(:${PANEL_PORT})?[[:space:]]*\\{" "$CADDY_FILE"; then
    # Replace legacy HY2 Caddyfile with import-based layout.
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
  caddy validate --config "$CADDY_FILE" || die "Caddy 配置校验失败"
  configure_fail2ban_panel "$PANEL_PATH"
  log "Caddy 站点配置：${site_file}"
}
