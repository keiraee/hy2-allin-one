#!/usr/bin/env bash
# backend.sh - 后端 Python 服务安装

write_backend() {
  local src="" mod="" mod_src="" candidate
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
  for mod in common.py subscription.py activity.py backup_ops.py; do
    mod_src=""
    for candidate in \
      "${SCRIPT_DIR:-}/app/${mod}" \
      "/usr/local/lib/hy2-aio/modules/app/${mod}"; do
      if [ -n "$candidate" ] && [ -s "$candidate" ]; then
        mod_src="$candidate"
        break
      fi
    done
    [ -n "$mod_src" ] || die "找不到后端模块：app/${mod}（请重新执行 hy2 upgrade）"
    install -m 0644 "$mod_src" "${APP_DIR}/${mod}"
  done
  install -m 0755 "$src" "$APP_FILE"
}
