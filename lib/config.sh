#!/usr/bin/env bash
# config.sh - Hysteria/Caddy/systemd 配置生成

write_rebuild_helper() {
  local src="" common_src="" candidate
  for candidate in \
    "${SCRIPT_DIR:-}/app/rebuild_config.py" \
    "/usr/local/lib/hy2-aio/modules/app/rebuild_config.py"; do
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      src="$candidate"
      break
    fi
  done
  [ -n "$src" ] || die "找不到配置重建脚本：app/rebuild_config.py（请重新执行 hy2 upgrade）"
  install -d -m 0755 "$APP_DIR"
  for candidate in \
    "${SCRIPT_DIR:-}/app/common.py" \
    "/usr/local/lib/hy2-aio/modules/app/common.py"; do
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      common_src="$candidate"
      break
    fi
  done
  [ -n "$common_src" ] && install -m 0644 "$common_src" "${APP_DIR}/common.py"
  install -m 0755 "$src" "$REBUILD_FILE"
}

write_xray_rebuild_helper() {
  local src="" candidate
  for candidate in \
    "${SCRIPT_DIR:-}/app/rebuild_xray.py" \
    "/usr/local/lib/hy2-aio/modules/app/rebuild_xray.py"; do
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      src="$candidate"
      break
    fi
  done
  [ -n "$src" ] || die "找不到 Xray 重建脚本：app/rebuild_xray.py（请重新执行 hy2 upgrade）"
  install -d -m 0755 "$APP_DIR"
  install -m 0755 "$src" "$XRAY_REBUILD_FILE"
}

write_systemd() {
  # systemd-journal 组并非处处存在；缺组时写死会让 hy2-aio 起不来，
  # 有该组才授予，日志解析/导出降级但服务必须能启动。
  local supplementary="hysteria caddy"
  if getent group systemd-journal >/dev/null 2>&1; then
    supplementary="${supplementary} systemd-journal"
  fi
  cat > "$SERVICE_FILE" <<EOF
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
SupplementaryGroups=${supplementary}
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
ReadOnlyPaths=/usr/local/lib/hy2-aio -/etc/caddy

[Install]
WantedBy=multi-user.target
EOF

  cat > "$RELOAD_PATH_FILE" <<'EOF'
[Unit]
Description=Watch HY2 AIO request to reload Hysteria

[Path]
PathExists=/run/hy2-aio/reload-hysteria
Unit=hy2-aio-reload-hysteria.service

[Install]
WantedBy=multi-user.target
EOF

  cat > "$RELOAD_SERVICE_FILE" <<EOF
[Unit]
Description=Control hysteria-server for HY2 AIO
After=hysteria-server.service

[Service]
Type=oneshot
ExecStart=${HYSTERIA_CONTROL_FILE}
EOF

  install -d -m 0755 "$APP_DIR"
  cat > "$HYSTERIA_CONTROL_FILE" <<'EOF'
#!/bin/sh
set -eu
cmd_file=/run/hy2-aio/hysteria-cmd
flag=/run/hy2-aio/reload-hysteria
cmd=restart
if [ -f "$cmd_file" ]; then
  cmd=$(tr -d ' \n\r\t' < "$cmd_file")
fi
case "$cmd" in
  stop)
    /bin/systemctl stop hysteria-server.service
    ;;
  start)
    /bin/systemctl start hysteria-server.service
    ;;
  restart)
    /bin/systemctl restart hysteria-server.service
    ;;
  port:*)
    # 格式 port:<hy2|vless>:<端口或范围>
    # 面板改端口走这里（root 权限）：改 env → 重建 → 重启，含 NAT 链清理。
    p_target=$(printf '%s' "$cmd" | cut -d: -f2)
    p_value=$(printf '%s' "$cmd" | cut -d: -f3-)
    res_file=/run/hy2-aio/port-result
    rm -f "$res_file"
    if [ -x /usr/local/bin/hy2 ]; then
      p_err=$(/usr/local/bin/hy2 port "$p_target" "$p_value" 2>&1 >/dev/null) && p_rc=0 || p_rc=$?
      if [ "$p_rc" -eq 0 ]; then
        printf 'OK\n' > "$res_file"
      else
        p_msg=$(printf '%s\n' "$p_err" | sed 's/\x1b\[[0-9;]*m//g; s/^\[ERROR\] *//' | awk 'NF{line=$0} END{print line}')
        printf 'ERR:%s\n' "${p_msg:-端口变更失败}" > "$res_file"
      fi
    else
      printf 'ERR:找不到 /usr/local/bin/hy2\n' > "$res_file"
    fi
    chmod 0644 "$res_file" 2>/dev/null || :
    ;;
  *)
    /bin/systemctl restart hysteria-server.service
    ;;
esac
rm -f "$cmd_file" "$flag"
EOF
  chmod 0755 "$HYSTERIA_CONTROL_FILE"

  install -d -m 0755 "$HYSTERIA_DROPIN_DIR"
  cat > "$HYSTERIA_DROPIN_FILE" <<EOF
[Unit]
ConditionPathExists=!${HY2_OFF_FILE}
EOF

  cat > "$XRAY_PRESTART_FILE" <<EOF
#!/bin/bash
set -Eeuo pipefail
# hy2-xray 启动前回收 VLESS TCP 端口：清掉残留官方 Xray，防止 bind 冲突导致无限重启。
. ${APP_DIR}/modules/lib/core.sh
read_env
reclaim_vless_tcp_port
EOF
  chmod 0755 "$XRAY_PRESTART_FILE"

  cat > "$XRAY_SERVICE_FILE" <<'EOF'
[Unit]
Description=HY2 AIO Xray VLESS+Reality
Documentation=https://github.com/XTLS/Xray-core
After=network-online.target xray.service xray@.service
Wants=network-online.target
Conflicts=xray.service xray@.service

[Service]
Type=simple
User=hy2-aio
Group=hy2-aio
ExecStartPre=+/usr/local/lib/hy2-aio/xray-prestart.sh
ExecStart=/usr/local/bin/xray run -c /etc/hy2-aio/xray.json
Restart=always
RestartSec=3
LimitNOFILE=1048576
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
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
ReadOnlyPaths=/etc/hy2-aio /usr/local/bin/xray
# Do not bind /run/hy2-aio: that RuntimeDirectory belongs to hy2-aio.service
# and disappears while it restarts, which makes Xray fail with NAMESPACE 226.

[Install]
WantedBy=multi-user.target
EOF

  cat > "$XRAY_RELOAD_PATH_FILE" <<'EOF'
[Unit]
Description=Watch HY2 AIO request to reload Xray

[Path]
PathExists=/run/hy2-aio/reload-xray
Unit=hy2-aio-reload-xray.service

[Install]
WantedBy=multi-user.target
EOF

  cat > "$XRAY_RELOAD_SERVICE_FILE" <<EOF
[Unit]
Description=Control hy2-xray for HY2 AIO
After=hy2-xray.service

[Service]
Type=oneshot
ExecStart=${XRAY_CONTROL_FILE}
EOF

  cat > "$XRAY_CONTROL_FILE" <<'EOF'
#!/bin/sh
set -eu
cmd_file=/run/hy2-aio/xray-cmd
flag=/run/hy2-aio/reload-xray
cmd=restart
if [ -f "$cmd_file" ]; then
  cmd=$(tr -d ' \n\r\t' < "$cmd_file")
fi
case "$cmd" in
  stop)
    /bin/systemctl stop hy2-xray.service
    ;;
  start)
    /bin/systemctl start hy2-xray.service
    ;;
  restart)
    /bin/systemctl restart hy2-xray.service
    ;;
  *)
    /bin/systemctl restart hy2-xray.service
    ;;
esac
rm -f "$cmd_file" "$flag"
EOF
  chmod 0755 "$XRAY_CONTROL_FILE"
}

ensure_hysteria_user() {
  # 官方 get-hy2.sh 的 hysteria-server.service 用 WorkingDirectory=~（用户家目录），
  # 家目录必须真实存在，否则服务启动 CHDIR 失败。
  getent group hysteria >/dev/null 2>&1 || groupadd --system hysteria
  local home="${HYSTERIA_HOME_DIR:-/var/lib/hysteria}" current
  if ! id hysteria >/dev/null 2>&1; then
    useradd --system --gid hysteria --home-dir "$home" --create-home --shell /usr/sbin/nologin hysteria
    install -d -o hysteria -g hysteria -m 0750 "$home"
    return
  fi
  current="$(getent passwd hysteria | cut -d: -f6)" || true
  case "$current" in
    ""|/nonexistent|/dev/null|/false)
      usermod -d "$home" hysteria
      current="$home"
      ;;
  esac
  [ -d "$current" ] || install -d -o hysteria -g hysteria -m 0750 "$current"
}

ensure_hy2_aio_user() {
  getent group hy2-aio >/dev/null 2>&1 || groupadd --system hy2-aio
  getent group hysteria >/dev/null 2>&1 || groupadd --system hysteria
  getent group caddy >/dev/null 2>&1 || groupadd --system caddy
  local extra_groups="hysteria,caddy"
  getent group systemd-journal >/dev/null 2>&1 && extra_groups="${extra_groups},systemd-journal"
  if ! id hy2-aio >/dev/null 2>&1; then
    useradd --system --gid hy2-aio --groups "$extra_groups" \
      --home-dir "$STATE_DIR" --shell /usr/sbin/nologin hy2-aio
  else
    usermod -a -G "$extra_groups" hy2-aio 2>/dev/null || true
  fi
  install -d -o hy2-aio -g hy2-aio -m 0750 "$STATE_DIR" "$STATE_DIR/backups"
  install -d -o hy2-aio -g caddy -m 2750 "$WEB_DIR" "$WEB_DIR/downloads"
  # Group-writable so unprivileged backend can update users.json / mode atomically.
  install -d -o root -g hy2-aio -m 0770 "$CONFIG_DIR"
  install -d -o hysteria -g hysteria -m 2770 /etc/hysteria
  chown root:hy2-aio "$CONFIG_DIR" 2>/dev/null || true
  chmod 0770 "$CONFIG_DIR" 2>/dev/null || true
  chown hysteria:hysteria /etc/hysteria 2>/dev/null || true
  chmod 2770 /etc/hysteria 2>/dev/null || true
  # Allow hy2-aio (in hysteria group) to rewrite config.yaml via rebuild helper.
  if [ -f /etc/hysteria/config.yaml ]; then
    chown hysteria:hysteria /etc/hysteria/config.yaml
    chmod 0660 /etc/hysteria/config.yaml
  fi
  chown hy2-aio:hy2-aio "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  chmod 0640 "$USERS_FILE" "$MODE_FILE" 2>/dev/null || true
  if [ -f "$XRAY_CONFIG" ]; then
    chown hy2-aio:hy2-aio "$XRAY_CONFIG" 2>/dev/null || true
    chmod 0640 "$XRAY_CONFIG" 2>/dev/null || true
  fi
}

caddy_auth_directive() {
  local version major minor
  # 解析 Caddy 版本号，处理 v 前缀（如 "v2.8.4" → "2 8"）
  version="$(caddy version 2>/dev/null | sed -E 's/^v?([0-9]+)\.([0-9]+).*/\1 \2/' || true)"
  major="$(awk '{print $1}' <<<"$version")"
  minor="$(awk '{print $2}' <<<"$version")"
  # Caddy 2.8+ 将 basicauth 更名为 basic_auth；解析失败时 minor 默认 6，走旧指令 basicauth
  if [ "${major:-2}" -gt 2 ] || { [ "${major:-2}" -eq 2 ] && [ "${minor:-6}" -ge 8 ]; }; then
    echo basic_auth
  else
    echo basicauth
  fi
}

caddyfile_has_legacy_hy2_site() {
  local caddyfile="${1:-$CADDY_FILE}"
  [ -f "$caddyfile" ] || return 1
  DOMAIN="$DOMAIN" PANEL_PORT="${PANEL_PORT:-443}" WEB_DIR="$WEB_DIR" \
    python3 - "$caddyfile" <<'PY'
import os
import re
import sys
from pathlib import Path

caddyfile = Path(sys.argv[1])
text = caddyfile.read_text(encoding="utf-8")
web_dir = os.environ.get("WEB_DIR", "")
if web_dir and web_dir in text:
    raise SystemExit(0)

domain = os.environ["DOMAIN"]
port = str(os.environ.get("PANEL_PORT") or "443")
domain_re = re.escape(domain)
port_suffix = rf":{re.escape(port)}" if port else ""
pattern = re.compile(rf"^{domain_re}(?:{port_suffix})?\s*\{{", re.MULTILINE)
raise SystemExit(0 if pattern.search(text) else 1)
PY
}

write_caddy() {
  local auth site_file marker
  panel_port_is_valid "${PANEL_PORT:-}" \
    || die "面板端口 ${PANEL_PORT:-<empty>} 无效或不安全；管理面板仅支持 HTTPS，禁止使用 80"
  auth="$(caddy_auth_directive)"
  site_file="$CADDY_SITE_FILE"
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

  # 密码只走进程环境（environ 仅属主可读）；不进 env/子进程 argv（argv 全员可见）。
  # BACKEND_HOST/PORT 是 readonly 常量且非密钥，沿用 env 传给子进程（v1.3.22 同款约束）。
  (
    export DOMAIN="$DOMAIN" PANEL_PORT="$PANEL_PORT" PANEL_PATH="$PANEL_PATH"
    export PANEL_USER="$PANEL_USER" PANEL_PASS="$PANEL_PASS" API_SECRET="$API_SECRET"
    export WEB_DIR="$WEB_DIR" AUTH_DIRECTIVE="$auth" SITE_FILE="$site_file"
    env BACKEND_HOST="$BACKEND_HOST" BACKEND_PORT="$BACKEND_PORT" \
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
backend_host = os.environ["BACKEND_HOST"]
backend_port = os.environ["BACKEND_PORT"]

password_hash = subprocess.check_output(
    ["caddy", "hash-password"],
    # caddy 非 TTY 分支按行读（ReadBytes('\n')），无尾部换行会报 "Error: EOF"。
    input=panel_pass + "\n",
    text=True,
).strip()

port = str(port or "443")
if port == "443":
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
        format json
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
            reverse_proxy {backend_host}:{backend_port} {{
                header_up X-API-Secret "{api_secret}"
                header_up X-Forwarded-For {{remote_host}}
                header_up X-Real-IP {{remote_host}}
                transport http {{
                    dial_timeout 3s
                    response_header_timeout 90s
                    read_timeout 90s
                }}
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
                Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            }}
            root * {web_dir}
            file_server
        }}

        handle /s/* {{
            reverse_proxy {backend_host}:{backend_port} {{
                header_up X-Forwarded-For {{remote_host}}
                header_up X-Real-IP {{remote_host}}
            }}
        }}

        # 兼容旧分拆版订阅：https://域名/{{TOKEN}}（无 /s/ 前缀）
        @legacy_sub path_regexp ^/[A-Fa-f0-9]{{32,64}}$
        handle @legacy_sub {{
            rewrite * /s{{http.request.uri.path}}
            reverse_proxy {backend_host}:{backend_port} {{
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
  )
  [ -f "$site_file" ] || die "写入 ${site_file} 失败"
  # Caddy runs as user `caddy`; umask 077 would otherwise leave 0600 and break import.
  chmod 0755 /etc/caddy
  chown root:caddy "$site_file"
  chmod 0640 "$site_file"

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
  elif caddyfile_has_legacy_hy2_site "$CADDY_FILE"; then
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
  chown root:caddy "$site_file"
  chmod 0640 "$site_file"
  chmod 0644 "$CADDY_FILE" 2>/dev/null || true
  caddy validate --config "$CADDY_FILE" || die "Caddy 配置校验失败"
  configure_fail2ban_panel "$PANEL_PATH"
  log "Caddy 站点配置：${site_file}"
}
