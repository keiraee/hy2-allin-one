#!/usr/bin/env bash
# backend.sh - 后端 Python 服务安装

write_backend() {
  local src="" candidate
  for candidate in \
    "${SCRIPT_DIR:-}/app/server.py" \
    "/usr/local/lib/hy2-aio/modules/app/server.py"; do
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      src="$candidate"
      break
    fi
  done
  [ -n "$src" ] || die "找不到后端源码：app/server.py（请重新执行 hy2 upgrade）"
  install -d -m 0755 "$APP_DIR"
  install -m 0755 "$src" "$APP_FILE"
}
