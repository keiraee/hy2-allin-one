#!/usr/bin/env bash
# cert.sh - 证书管理

create_certificate() {
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
