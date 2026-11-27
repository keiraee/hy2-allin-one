#!/usr/bin/env bash
# backend.sh - 后端 Python 服务安装

write_backend() {
  local src="" common_src="" candidate
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
  for candidate in \
    "${SCRIPT_DIR:-}/app/common.py" \
    "/usr/local/lib/hy2-aio/modules/app/common.py"; do
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      common_src="$candidate"
      break
    fi
  done
  [ -n "$common_src" ] || die "找不到公共模块：app/common.py（请重新执行 hy2 upgrade）"
  install -m 0644 "$common_src" "${APP_DIR}/common.py"
  install -m 0755 "$src" "$APP_FILE"
}
