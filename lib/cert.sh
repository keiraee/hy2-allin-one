#!/usr/bin/env bash
# cert.sh - 证书管理

# 把 Caddy 已经申请下来的 Let's Encrypt 证书复制给 Hysteria 用。
#
# 为什么必须这么做：Hysteria 原来一律用 openssl 自签，SAN 只有 IP。
# 结果任何做严格 TLS 校验的客户端都会报
#   "certificate is not valid for any names" / "signed by unknown authority"
# —— 只能靠 insecure 硬绕过。而 Caddy 那边明明有 Let's Encrypt 真证书。
#
# 复用之后：客户端可以 sni=域名 + insecure=false，真校验通过；
# 也不用再吃 Clash 系 2026.8.1 弃用 allowInsecure 的警告。
# 证书到期由 Caddy 自动续，Hysteria 读的是拷贝，重启即生效。
#
# 找不到 Caddy 证书（还没申请成功 / 纯 IP 部署）时返回非零，调用方退回自签。
reuse_caddy_certificate() {
  local domain="${DOMAIN:-}"
  [ -n "$domain" ] || return 1
  local base="${CADDY_DATA_DIR:-/var/lib/caddy}"
  local crt key dir issuer
  # Caddy 的证书目录在不同发行版有两处布局，都要试
  for dir in "$base"/certificates/*/"$domain" "$base"/.local/share/caddy/certificates/*/"$domain"; do
    [ -d "$dir" ] || continue
    crt="$dir/$domain.crt"
    key="$dir/$domain.key"
    [ -s "$crt" ] && [ -s "$key" ] || continue
    issuer="$(openssl x509 -in "$crt" -noout -issuer 2>/dev/null || true)"
    case "$issuer" in
      *[Cc]addy*[Ll]ocal*[Aa]uthority*) continue ;;   # 本地 CA 不算数
    esac
    install -d -o hysteria -g hysteria -m 2770 /etc/hysteria
    install -o hysteria -g hysteria -m 0640 "$crt" "$HYSTERIA_CERT"
    install -o hysteria -g hysteria -m 0640 "$key" "$HYSTERIA_KEY"
    log "Hysteria 复用 Caddy 证书：${domain}"
    return 0
  done
  return 1
}

create_certificate() {
  # 优先复用具名证书；拿不到才自签（纯 IP 部署 / Caddy 还没申请成功）
  if reuse_caddy_certificate; then
    return 0
  fi
  install -d -o hysteria -g hysteria -m 2770 /etc/hysteria
  openssl req -x509 -nodes \
    -newkey ec \
    -pkeyopt ec_paramgen_curve:prime256v1 \
    -keyout "$HYSTERIA_KEY" \
    -out "$HYSTERIA_CERT" \
    -days 3650 \
    -subj "/CN=${PUBLIC_IP}" \
    -addext "subjectAltName=IP:${PUBLIC_IP}" >/dev/null 2>&1
  chown hysteria:hysteria "$HYSTERIA_CERT" "$HYSTERIA_KEY"
  chmod 0640 "$HYSTERIA_CERT"
  chmod 0640 "$HYSTERIA_KEY"
}
