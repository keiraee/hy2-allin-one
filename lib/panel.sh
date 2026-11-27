#!/usr/bin/env bash
# panel.sh - Web 面板 HTML 生成

# 面板字体：自托管 Inter + JetBrains Mono（各两个字重，共约 91KB）。
#
# 为什么自托管而不是走 Google Fonts / jsdelivr：
#   面板的 CSP 是 default-src 'self'，跨域字体直接被拦；走同源就绕开了
#   这条限制，也顺带免掉第三方 CDN 在国内的可用性和隐私问题。
#
# 为什么只装 latin 子集：
#   中文有上万字，任何一个 CJK webfont 都是几 MB 起。面板正文用系统中文
#   字体（字体栈里排在 Inter 后面），webfont 只负责拉丁字母和数字——
#   面板 90% 的内容（端口、IP、流量数值、用户名）正好都在这个范围里。
#
# 为什么是「可选」：
#   字体下载失败绝不能让 install/repair 挂掉。缺了字体，HTML 里的字体栈
#   会自动退到系统字体，功能一切正常，只是少了统一感。
PANEL_FONT_DIR="${WEB_DIR}/fonts"
# 文件名 + 期望 sha256。字体是二进制、不进 SHA256SUMS（那份清单只登记
# bin/*.sh 和 lib/*.sh 模块，混入二进制会打破既有校验约定），
# 所以哈希直接写在这儿，下载后逐文件比对，防止半截文件或 CDN 投毒。
PANEL_FONT_FILES=(
  "inter-400.woff2|dd05e326cf8eac3b55acecf29c842ed73e6e6dd06491cf47f7e8800680ab3e33"
  "inter-600.woff2|62553d159189834af73c9a6264704be5b2bee9a08da66a14768d8e5c6ffd2cdb"
  "jetbrains-mono-400.woff2|7c53386f55c866c1b4c9309c4bcf74eda10896aab3a1780b0af5cc4976e27a27"
  "jetbrains-mono-700.woff2|ed8b8f71b22bf3b6e1ec1cf9b24dd999785aae33d6256950c1f86c97e423b6ef"
)

# 客户端图标（Clash / v2ray / sing-box），给订阅菜单用。
#
# 和字体一样是可选资源：下载失败就退回内置的 sprite 图标，功能不受影响。
# 32px 给普通屏，64px 给 Retina；两个尺寸都带，避免高分屏糊成一团。
PANEL_ICON_DIR="${WEB_DIR}/icons"
PANEL_ICON_FILES=(
  "clash-32.webp|1482f12264af701d839c618859bf740ae768b03cfb64e6a837116b3c5b77f57c"
  "clash-64.webp|5a657f2c7353ce218e86839faecfc0fd4783d8d7da51dff1ac0ff259ee79e7f3"
  "v2ray-32.webp|98751a83cc4ac3a47fcd3a88c595959cc1fcd2190704d7345cea9d1b2414e948"
  "v2ray-64.webp|8650d0b9af6425df7ef897968ba256522d3356f3e52717bd2f602ce879e6fede"
  "singbox-32.webp|66aef8aab28d4a213c9705d693ac516c7c207c44b9168ba1c5ea1aa6273d1fea"
  "singbox-64.webp|221d3ffa1e803d60c4ca94d905b524d8f13384c25be13da3226ce5145798a367"
)

# 二维码库（qrcode-generator，MIT）。
#
# 为什么放成独立文件而不是内联进 HTML：
#   - 内联会让每次加载面板都多传 20KB（面板本身才 92KB）
#   - 独立文件同源加载，CSP 的 script-src 'self' 允许
#   - 浏览器会缓存它，第二次打开就不用再传
#
# 为什么不用服务端生成：目标机是 4GB 小机器，不能为了二维码去装
# qrcode/Pillow 这类依赖。浏览器端生成，服务端零改动。
PANEL_VENDOR_DIR="${WEB_DIR}/vendor"
PANEL_VENDOR_FILES=(
  "4ee9e4db9666ed5c38c508c0cb57512465fcbc5a653ebf9fa33c0c37c71b15bf  qrcode.min.js"
)

_panel_curl() {
  if declare -F _bootstrap_curl >/dev/null 2>&1; then
    _bootstrap_curl "$@"
  else
    curl -fsSL --retry 3 --retry-delay 2 \
      -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' "$@"
  fi
}

install_panel_vendor() {
  local force="${1:-0}" name want got tmp ok=0 repo_base="${HY2_REPO_URL:-${REPO_URL:-}}"
  install -d -o hy2-aio -g caddy -m 2750 "$PANEL_VENDOR_DIR" 2>/dev/null || return 1

  for entry in "${PANEL_VENDOR_FILES[@]}"; do
    want="${entry%% *}"; name="${entry##* }"
    if [ "$force" != "1" ] && [ -s "${PANEL_VENDOR_DIR}/${name}" ] \
      && [ "$(font_sha256 "${PANEL_VENDOR_DIR}/${name}")" = "$want" ]; then
      continue
    fi
    local local_dir="${SCRIPT_DIR:-/usr/local/lib/hy2-aio/modules}/assets/vendor"
    if [ -s "${local_dir}/${name}" ] && [ "$(font_sha256 "${local_dir}/${name}")" = "$want" ]; then
      install -m 0640 -o hy2-aio -g caddy "${local_dir}/${name}" "${PANEL_VENDOR_DIR}/${name}"
      ok=$((ok + 1))
      continue
    fi
    tmp="$(mktemp)"
    # 拉取顺序:GitHub raw → jsdelivr CDN 镜像。国内 VPS 直连
    # raw.githubusercontent.com 经常超时,静默失败后面板二维码永远装不上
    # (真机踩过)。镜像内容和 raw 同源,SHA256 校验兜住一致性。
    local fetch_urls=()
    if [ -n "$repo_base" ]; then
      fetch_urls+=("${repo_base%/}/assets/vendor/${name}?nocache=$(date +%s)")
    fi
    fetch_urls+=("https://testingcf.jsdelivr.net/gh/keiraee/hy2-allin-one@main/assets/vendor/${name}")
    local fetch_url
    for fetch_url in "${fetch_urls[@]}"; do
      if _panel_curl "$fetch_url" -o "$tmp" 2>/dev/null \
        && [ -s "$tmp" ] && head -c 200 "$tmp" | grep -q 'qrcode'; then
        got="$(font_sha256 "$tmp")"
        if [ "$got" = "$want" ]; then
          install -m 0640 -o hy2-aio -g caddy "$tmp" "${PANEL_VENDOR_DIR}/${name}"
          ok=$((ok + 1))
          break
        else
          warn "二维码库校验不符，尝试下一个来源"
        fi
      fi
    done
    rm -f "$tmp"
  done
  [ "$ok" -gt 0 ] && log "面板依赖就绪（二维码）"
  return 0
}

install_panel_icons() {
  local force="${1:-0}" missing=() name want got tmp ok=0 repo_base="${HY2_REPO_URL:-${REPO_URL:-}}"
  install -d -o hy2-aio -g caddy -m 2750 "$PANEL_ICON_DIR" 2>/dev/null || return 1

  if [ "$force" != "1" ]; then
    for entry in "${PANEL_ICON_FILES[@]}"; do
      name="${entry%%|*}"
      [ -s "${PANEL_ICON_DIR}/${name}" ] || missing+=("$entry")
    done
    [ "${#missing[@]}" -eq 0 ] && return 0
  else
    missing=("${PANEL_ICON_FILES[@]}")
  fi

  local local_dir="${SCRIPT_DIR:-/usr/local/lib/hy2-aio/modules}/assets/icons"
  for entry in "${missing[@]}"; do
    name="${entry%%|*}"; want="${entry##*|}"
    if [ -s "${local_dir}/${name}" ] && [ "$(font_sha256 "${local_dir}/${name}")" = "$want" ]; then
      install -m 0640 -o hy2-aio -g caddy "${local_dir}/${name}" "${PANEL_ICON_DIR}/${name}"
      ok=$((ok + 1))
      continue
    fi
    [ -n "$repo_base" ] || continue
    tmp="$(mktemp)"
    # WebP 魔数：RIFF....WEBP
    if _panel_curl "${repo_base%/}/assets/icons/${name}?nocache=$(date +%s)" -o "$tmp" 2>/dev/null \
      && [ -s "$tmp" ] && head -c4 "$tmp" | grep -q 'RIFF'; then
      got="$(font_sha256 "$tmp")"
      if [ "$got" = "$want" ]; then
        install -m 0640 -o hy2-aio -g caddy "$tmp" "${PANEL_ICON_DIR}/${name}"
        ok=$((ok + 1))
      else
        warn "图标 ${name} 校验不符，已丢弃"
      fi
    fi
    rm -f "$tmp"
  done
  [ "$ok" -gt 0 ] && log "面板图标就绪（Clash / v2ray / sing-box）"
  return 0
}

font_sha256() {
  python3 -c 'import hashlib,sys,pathlib; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$1" 2>/dev/null
}

install_panel_fonts() {
  local force="${1:-0}" missing=() name base repo_base="${HY2_REPO_URL:-${REPO_URL:-}}"
  install -d -o hy2-aio -g caddy -m 2750 "$PANEL_FONT_DIR"

  # 已经齐全就不重复下载：repair 很频繁，每次都拉 91KB 没必要
  if [ "$force" != "1" ]; then
    for entry in "${PANEL_FONT_FILES[@]}"; do
      name="${entry%%|*}"
      [ -s "${PANEL_FONT_DIR}/${name}" ] || missing+=("$entry")
    done
    [ "${#missing[@]}" -eq 0 ] && return 0
  else
    missing=("${PANEL_FONT_FILES[@]}")
  fi

  # 本地仓库检出（开发模式）优先用仓库里的副本，免去一次网络往返；
  # 正式安装时 modules 目录里也带着 assets/fonts，同样能命中。
  local local_dir="${SCRIPT_DIR:-/usr/local/lib/hy2-aio/modules}/assets/fonts"
  local tmp ok=0 want got
  for entry in "${missing[@]}"; do
    name="${entry%%|*}"
    want="${entry##*|}"
    # 先试本地副本
    if [ -s "${local_dir}/${name}" ] && [ "$(font_sha256 "${local_dir}/${name}")" = "$want" ]; then
      install -m 0640 -o hy2-aio -g caddy "${local_dir}/${name}" "${PANEL_FONT_DIR}/${name}"
      ok=$((ok + 1))
      continue
    fi
    # 再试远程（按当前 commit 钉住，避免 CDN 缓存旧文件）
    [ -n "$repo_base" ] || continue
    tmp="$(mktemp)"
    if _panel_curl "${repo_base%/}/assets/fonts/${name}?nocache=$(date +%s)" -o "$tmp" 2>/dev/null \
      && [ -s "$tmp" ] \
      && head -c4 "$tmp" | grep -q 'wOF2'; then
      got="$(font_sha256 "$tmp")"
      if [ "$got" = "$want" ]; then
        install -m 0640 -o hy2-aio -g caddy "$tmp" "${PANEL_FONT_DIR}/${name}"
        ok=$((ok + 1))
      else
        warn "字体 ${name} 校验不符（期望 ${want:0:12}… 实际 ${got:0:12}…），已丢弃"
      fi
    fi
    rm -f "$tmp"
  done

  if [ "$ok" -eq "${#missing[@]}" ]; then
    log "面板字体就绪（Inter + JetBrains Mono）"
  else
    # 不 die：字体是可选的，缺了只是回退到系统字体
    warn "面板字体未装全（$(( ${#missing[@]} - ok ))/${#missing[@]} 失败），将回退到系统字体"
  fi
  return 0
}

write_panel() {
  local src="" candidate
  for candidate in \
    "${SCRIPT_DIR:-}/web/index.html" \
    "/usr/local/lib/hy2-aio/modules/web/index.html"; do
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      src="$candidate"
      break
    fi
  done
  [ -n "$src" ] || die "找不到面板模板：web/index.html（请重新执行 hy2 upgrade）"
  install -d -o hy2-aio -g caddy -m 2750 "$WEB_DIR" "$WEB_DIR/downloads" "$WEB_DIR/rules"
  log "写入面板：${WEB_DIR}/index.html"
  install -m 0640 -o hy2-aio -g caddy "$src" "$WEB_DIR/index.html"

  chown -R hy2-aio:caddy "$WEB_DIR"
  find "$WEB_DIR" -type d -exec chmod 2750 {} \;
  find "$WEB_DIR" -type f -exec chmod 0640 {} \;
  # 字体放在 HTML 写完之后：即使字体装不上，面板本身已经可用了
  install_panel_fonts || true
  install_panel_icons || true
  install_panel_vendor || true
}
