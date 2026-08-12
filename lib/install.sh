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
  command -v caddy >/dev/null 2>&1 && return
  if [ "$PKG_MANAGER" = "apt" ]; then
    install_caddy
    return
  fi
  "$PKG_MANAGER" install -y caddy >/dev/null 2>&1 || true
  if ! command -v caddy >/dev/null 2>&1; then
    local arch
    case "$(uname -m)" in
      x86_64) arch=amd64 ;;
      aarch64|arm64) arch=arm64 ;;
      *) die "不支持的 CPU 架构：$(uname -m)" ;;
    esac
    curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=$arch" -o /tmp/caddy
    install -m 0755 /tmp/caddy /usr/local/bin/caddy
    rm -f /tmp/caddy
  fi
  getent group caddy >/dev/null 2>&1 || groupadd --system caddy
  id caddy >/dev/null 2>&1 || useradd --system --gid caddy --home /var/lib/caddy --shell /usr/sbin/nologin caddy
  install -d -o caddy -g caddy -m 0750 /var/lib/caddy /var/log/caddy
  cat > /etc/systemd/system/caddy.service <<'EOF'
[Unit]
Description=Caddy
After=network-online.target
Wants=network-online.target
[Service]
User=caddy
Group=caddy
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable caddy.service >/dev/null
  command -v caddy >/dev/null 2>&1 || die "Caddy 安装失败"
}

configure_firewall_v12() {
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
  if command -v hysteria >/dev/null 2>&1; then
    log "Hysteria 已存在：$(hysteria version 2>/dev/null | head -1 || true)"
    return
  fi
  log "通过官方脚本安装 Hysteria 2"
  bash <(curl -fsSL https://get.hy2.sh/)
  command -v hysteria >/dev/null 2>&1 || die "Hysteria 安装失败"
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
