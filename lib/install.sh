#!/usr/bin/env bash
# install.sh - 安装依赖和系统配置

install_packages_v12() {
  log "安装基础依赖"
  case "$PKG_MANAGER" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y curl ca-certificates openssl python3 jq tar gzip \
        iproute2 procps util-linux gpg debian-keyring debian-archive-keyring \
        apt-transport-https
      ;;
    dnf|yum)
      "$PKG_MANAGER" install -y curl ca-certificates openssl python3 jq tar gzip \
        iproute procps-ng util-linux gnupg2
      ;;
    zypper)
      zypper --non-interactive install curl ca-certificates openssl python3 jq tar gzip \
        iproute2 procps util-linux gpg2
      ;;
    *) die "不支持的包管理器：$PKG_MANAGER" ;;
  esac
}

install_caddy() {
  if command -v caddy >/dev/null 2>&1; then
    log "Caddy 已存在：$(caddy version 2>/dev/null || true)"
    return
  fi

  log "安装 Caddy"
  install -d -m 0755 /usr/share/keyrings /etc/apt/sources.list.d
  if curl -1fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor --batch --yes \
      -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1fsSL 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      -o /etc/apt/sources.list.d/caddy-stable.list; then
    chmod o+r \
      /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
      /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get install -y caddy
  else
    warn "Caddy 官方仓库添加失败，尝试系统仓库"
    apt-get install -y caddy
  fi
  command -v caddy >/dev/null 2>&1 || die "Caddy 安装失败"
}

install_caddy_v12() {
  local caddy_bin arch version ver asset tmp archive sums expected
  local unit_file="/etc/systemd/system/caddy.service" write_unit=0

  caddy_bin="$(command -v caddy 2>/dev/null || true)"
  if [ -z "$caddy_bin" ]; then
    case "$PKG_MANAGER" in
      apt) install_caddy ;;
      dnf|yum) "$PKG_MANAGER" install -y caddy >/dev/null 2>&1 || true ;;
      zypper) zypper --non-interactive install caddy >/dev/null 2>&1 || true ;;
      *) die "不支持的包管理器：$PKG_MANAGER" ;;
    esac
    caddy_bin="$(command -v caddy 2>/dev/null || true)"
  fi

  if [ -z "$caddy_bin" ]; then
    version="${CADDY_VERSION:-v2.11.4}"
    ver="${version#v}"
    case "$(uname -m)" in
      x86_64) arch=amd64 ;;
      aarch64|arm64) arch=arm64 ;;
      *) die "不支持的 CPU 架构：$(uname -m)" ;;
    esac
    asset="caddy_${ver}_linux_${arch}.tar.gz"
    tmp="$(mktemp -d)"
    archive="$tmp/$asset"
    sums="$tmp/checksums.txt"
    log "下载并校验 Caddy ${version}（${asset}）"
    curl -fsSL "https://github.com/caddyserver/caddy/releases/download/${version}/caddy_${ver}_checksums.txt" -o "$sums" \
      || { rm -rf "$tmp"; die "下载 Caddy checksums 失败"; }
    curl -fsSL "https://github.com/caddyserver/caddy/releases/download/${version}/${asset}" -o "$archive" \
      || { rm -rf "$tmp"; die "下载 Caddy 失败"; }
    expected="$(awk -v name="$asset" '$2 == name { print $1; exit }' "$sums")"
    [ -n "$expected" ] || { rm -rf "$tmp"; die "checksums 中找不到 ${asset}"; }
    python3 - "$archive" "$expected" <<'PY' || { rm -rf "$tmp"; die "Caddy SHA256 校验失败"; }
import hashlib, pathlib, sys
path = pathlib.Path(sys.argv[1])
expected = sys.argv[2].lower()
digest = hashlib.sha256(path.read_bytes()).hexdigest()
if digest != expected:
    raise SystemExit(f"got {digest}, want {expected}")
PY
    tar -xzf "$archive" -C "$tmp" caddy || { rm -rf "$tmp"; die "解压 Caddy 失败"; }
    install -m 0755 "$tmp/caddy" /usr/local/bin/caddy
    rm -rf "$tmp"
    command -v restorecon >/dev/null 2>&1 && restorecon /usr/local/bin/caddy 2>/dev/null || true
    caddy_bin="$(command -v caddy 2>/dev/null || true)"
  fi

  [ -n "$caddy_bin" ] && [ -x "$caddy_bin" ] || die "Caddy 安装失败"
  [[ "$caddy_bin" =~ ^/[A-Za-z0-9_./:+-]+$ ]] \
    || die "Caddy 二进制路径无效：$caddy_bin"
  "$caddy_bin" version >/dev/null 2>&1 || die "Caddy 二进制无法运行：$caddy_bin"

  getent group caddy >/dev/null 2>&1 || groupadd --system caddy
  id caddy >/dev/null 2>&1 || useradd --system --gid caddy --home /var/lib/caddy --shell /usr/sbin/nologin caddy
  install -d -o caddy -g caddy -m 0750 /var/lib/caddy /var/log/caddy

  # Preserve distro-provided units. Only create our own when none exists, or
  # repair the exact stale unit emitted by older HY2 AIO versions.
  systemctl daemon-reload
  if [ -f "$unit_file" ] \
    && grep -Fq 'ExecStart=/usr/local/bin/caddy ' "$unit_file" \
    && [ ! -x /usr/local/bin/caddy ]; then
    warn "检测到失效的旧 Caddy systemd 路径；改用 $caddy_bin"
    write_unit=1
  elif ! systemctl cat caddy.service >/dev/null 2>&1; then
    write_unit=1
  fi

  if [ "$write_unit" = "1" ]; then
    install -d -m 0755 "$(dirname "$unit_file")"
    cat > "$unit_file" <<EOF
[Unit]
Description=Caddy
After=network-online.target
Wants=network-online.target
[Service]
User=caddy
Group=caddy
ExecStart=${caddy_bin} run --environ --config /etc/caddy/Caddyfile
ExecReload=${caddy_bin} reload --config /etc/caddy/Caddyfile --force
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
  fi
  systemctl enable caddy.service >/dev/null
  systemctl cat caddy.service >/dev/null 2>&1 || die "Caddy systemd 服务缺失"
}

configure_fail2ban_panel() {
  local panel_path="$1" filter_file jail_file sample_file now check_output
  command -v fail2ban-client >/dev/null 2>&1 || return 0
  install -d -m 0755 /etc/fail2ban/filter.d /etc/fail2ban/jail.d
  filter_file="/etc/fail2ban/filter.d/hy2-caddy-auth.conf"
  jail_file="/etc/fail2ban/jail.d/hy2-caddy-auth.conf"

  cat > "$filter_file" <<EOF
[Definition]
datepattern = ^\{"level":"[a-z]+","ts":({EPOCH}),
failregex = ^(?:\{"level":"[a-z]+","ts":(?:[0-9]+(?:\.[0-9]+)?|\s*(?:\.[0-9]+)?),)?"logger":"http\.log\.access(?:\.[^"]+)?","msg":"handled request","request":\{"remote_ip":"<HOST>","remote_port":"[0-9]+","client_ip":"[^"]*","proto":"HTTP/[^"]+","method":"[^"]+","host":"[^"]+","uri":"/${panel_path}(?:[/?](?:\\\\.|[^"\\\\])*)?",.*\},"bytes_read":[0-9]+,"user_id":"[^"]*","duration":[^,]+,"size":[0-9]+,"status":401,.*\}\s*$
ignoreregex =
EOF

  cat > "$jail_file" <<'EOF'
[hy2-caddy-auth]
enabled = true
filter = hy2-caddy-auth
logpath = /var/log/caddy/hy2-aio.log
maxretry = 15
findtime = 300
bantime = 3600
EOF

  if command -v fail2ban-regex >/dev/null 2>&1; then
    sample_file="$(mktemp)"
    now="$(date +%s)"
    printf '%s\n' "{\"level\":\"info\",\"ts\":${now}.125,\"logger\":\"http.log.access.log0\",\"msg\":\"handled request\",\"request\":{\"remote_ip\":\"203.0.113.10\",\"remote_port\":\"43110\",\"client_ip\":\"203.0.113.10\",\"proto\":\"HTTP/2.0\",\"method\":\"GET\",\"host\":\"panel.example.com\",\"uri\":\"/${panel_path}/\",\"headers\":{},\"tls\":{\"version\":772}},\"bytes_read\":0,\"user_id\":\"\",\"duration\":0.001,\"size\":0,\"status\":401,\"resp_headers\":{}}" > "$sample_file"
    if ! check_output="$(fail2ban-regex "$sample_file" "$filter_file" --print-all-matched 2>/dev/null)" \
      || ! grep -Fq '"remote_ip":"203.0.113.10"' <<<"$check_output"; then
      rm -f "$sample_file"
      warn "fail2ban 过滤器自检失败；未启用 HY2 面板 jail"
      rm -f "$filter_file" "$jail_file"
      return 0
    fi
    rm -f "$sample_file"
  fi

  if ! fail2ban-client reload >/dev/null 2>&1 \
    && ! systemctl reload fail2ban >/dev/null 2>&1; then
    warn "fail2ban 配置已写入，但服务重载失败；HY2 面板 jail 尚未生效"
    return 0
  fi
  if ! fail2ban-client status hy2-caddy-auth >/dev/null 2>&1; then
    warn "fail2ban 配置已写入，但 HY2 面板 jail 未运行"
    return 0
  fi
  log "fail2ban 已生效：面板 Basic Auth 连续失败将封禁来源 IP"
}

configure_firewall_v12() {
  PANEL_PORT="${PANEL_PORT:-443}"
  HY2_PORT="${HY2_PORT:-443}"
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    ufw allow 80/tcp >/dev/null
    ufw allow "$PANEL_PORT/tcp" >/dev/null
    ufw allow "$HY2_PORT/udp" >/dev/null
    return
  fi
  if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=80/tcp >/dev/null
    firewall-cmd --permanent --add-port="$PANEL_PORT/tcp" >/dev/null
    firewall-cmd --permanent --add-port="$HY2_PORT/udp" >/dev/null
    firewall-cmd --reload >/dev/null
    return
  fi
  warn "防火墙未修改；如需要请手动放行 TCP 80、$PANEL_PORT 和 UDP $HY2_PORT"
}

install_hysteria() {
  local force="${1:-0}"
  if [ "$force" != "1" ] && command -v hysteria >/dev/null 2>&1; then
    log "Hysteria 已存在：$(hysteria version 2>/dev/null | head -1 || true)"
    return
  fi

  local version tag arch asset tmp hashes bin script expected
  version="${HYSTERIA_VERSION:-v2.12.1}"
  version="${version#app/}"
  tag="app/${version}"
  case "$(uname -m)" in
    x86_64) arch=amd64; asset=hysteria-linux-amd64 ;;
    aarch64|arm64) arch=arm64; asset=hysteria-linux-arm64 ;;
    *) die "不支持的 CPU 架构：$(uname -m)" ;;
  esac

  log "下载并校验 Hysteria ${version}（${asset}）"
  tmp="$(mktemp -d)"
  hashes="$tmp/hashes.txt"
  bin="$tmp/$asset"
  script="$tmp/get-hy2.sh"
  curl -fsSL "https://github.com/apernet/hysteria/releases/download/${tag}/hashes.txt" -o "$hashes" \
    || { rm -rf "$tmp"; die "下载 hashes.txt 失败"; }
  curl -fsSL "https://github.com/apernet/hysteria/releases/download/${tag}/${asset}" -o "$bin" \
    || { rm -rf "$tmp"; die "下载 Hysteria 二进制失败"; }
  expected="$(awk -v name="build/${asset}" '$2 == name { print $1; exit }' "$hashes")"
  [ -n "$expected" ] || { rm -rf "$tmp"; die "hashes.txt 中找不到 ${asset}"; }
  python3 - "$bin" "$expected" <<'PY' || { rm -rf "$tmp"; die "Hysteria SHA256 校验失败"; }
import hashlib, pathlib, sys
path = pathlib.Path(sys.argv[1])
expected = sys.argv[2].lower()
digest = hashlib.sha256(path.read_bytes()).hexdigest()
if digest != expected:
    raise SystemExit(f"got {digest}, want {expected}")
PY

  curl -fsSL https://get.hy2.sh/ -o "$script" || { rm -rf "$tmp"; die "下载官方安装脚本失败"; }
  grep -q 'hysteria' "$script" || { rm -rf "$tmp"; die "Hysteria 安装脚本校验失败"; }
  bash "$script" --local "$bin"
  rm -rf "$tmp"
  command -v hysteria >/dev/null 2>&1 || die "Hysteria 安装失败"
  log "Hysteria 已安装：$(hysteria version 2>/dev/null | head -1 || true)"
}

configure_swap_and_kernel() {
  log "配置 Swap、BBR 与 UDP 缓冲"
  local mem_kb
  mem_kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
  if [ "${mem_kb:-0}" -lt 1048576 ] && ! swapon --show --noheadings | grep -q .; then
    if [ ! -f /swapfile ]; then
      fallocate -l 1G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
    fi
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null 2>&1 || true
    swapon /swapfile || true
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi

  modprobe tcp_bbr 2>/dev/null || true
  echo tcp_bbr > /etc/modules-load.d/tcp_bbr.conf
  cat > /etc/sysctl.d/99-hy2-aio.conf <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.core.rmem_max=16777216
net.core.wmem_max=16777216
EOF
  /usr/sbin/sysctl --system >/dev/null 2>&1 || true
}
