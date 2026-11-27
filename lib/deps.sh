#!/usr/bin/env bash
# deps.sh - 运行环境自检：识别当前机器缺什么，并按发行版自动补齐
#
# 设计原则（小机器优先，宁可少装不可乱装）：
#   1. 只登记「本脚本的代码里真的会调用」的命令。没调用的东西不进清单——
#      清单里多一项，用户的小机器上就可能多一个不必要的包、多一个常驻服务。
#   2. 装了才用得上的（防火墙工具、fail2ban），未启用对应功能时一律不碰。
#   3. 明细只在 -v 时列出；默认输出只讲「缺什么、要不要管」。
#
# 两个入口：
#   hy2 deps       只体检，不改系统（退出码 0 = 当前功能所需的都齐了）
#   hy2 deps fix   只补「现在真跑不起来的」缺件，装不上的列出来

# 依赖清单：每行 7 段，用 | 分隔
#   命令 | apt包 | rpm包 | zypper包 | 级别 | 磁盘档次 | 何时才需要
# 级别：core = 缺了服务直接不可用 / feature = 只在某功能开启时才要
# 档次：small = 几 MB / large = 几十~上百 MB 且带常驻服务 / zero = 无独立包
# 何时才需要：
#   always           装本服务就一直要
#   hop              只在端口跳跃开启时要
#   ufw|firewalld    只在本机真的在用 ufw / firewalld 时才要（用于放行端口）
#   fail2ban         只在已经装了 fail2ban 时才要（面板登录保护）
#
# 刻意不收录的命令及理由（写在这免得以后又被人加回去）：
#   jq     —— 本脚本代码里一次都没调用过；解析 JSON 全靠 python3 -c。
#             老 install_packages_v12 里装着它纯属历史遗留。
#   gawk   —— awk 是 POSIX 必备（Debian 自带 mawk），不缺。
#   procps —— ps/free 只在状态展示用，缺了不影响服务；且 Debian 基础镜像自带。
DEPS_TABLE='
python3|python3|python3|python3|core|small|always
curl|curl|curl|curl|core|small|always
tar|tar|tar|tar|core|small|always
gzip|gzip|gzip|gzip|core|small|always
openssl|openssl|openssl|openssl|core|small|always
awk|gawk|gawk|gawk|core|small|always
grep|grep|grep|grep|core|small|always
sed|sed|sed|sed|core|small|always
ss|iproute2|iproute|iproute2|core|small|always
flock|util-linux|util-linux|util-linux|core|small|always
nft|nftables|nftables|nftables|feature|small|hop
iptables|iptables|iptables|iptables|feature|small|hop
ip6tables|iptables|iptables|iptables|feature|small|hop
firewall-cmd|firewalld|firewalld|firewalld|feature|large|firewalld
fail2ban-client|fail2ban|fail2ban|fail2ban|feature|large|fail2ban
'

# 每个命令在「这台机器上到底重不重要」，只看第 7 段「何时才需要」。
# 没到它出场的时候，缺了也跟本机能不能跑服务毫无关系。
deps_is_required() {
  local cmd="$1" level="$2" when="${3:-always}"
  [ "$level" = "core" ] && return 0
  case "$when" in
    always)
      return 0
      ;;
    hop)
      # 只有开了端口跳跃才真的要 NAT 重定向；没开的话 iptables/nft 缺不缺无所谓
      declare -F port_hop_enabled >/dev/null 2>&1 && port_hop_enabled
      return
      ;;
    firewalld)
      # 只在本机真的用 firewalld 时才需要它的命令行来放行端口
      command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1
      return
      ;;
    fail2ban)
      # 只有已经装了 fail2ban（自带 jail）才谈得上用它的客户端
      [ -d /etc/fail2ban ]
      return
      ;;
  esac
  return 1
}

# 识别当前这台机器是什么配置。装之前先把「我认出来你是什么机器」讲清楚，
# 比装到一半才炸内存（512MB 小机的经典坑）友好得多。
deps_print_device() {
  local arch mem_kb mem_mb disk_kb disk_gb os_name
  arch="$(uname -m 2>/dev/null || echo unknown)"
  case "$arch" in
    x86_64|amd64) arch="x86_64 (amd64)" ;;
    aarch64|arm64) arch="aarch64 (arm64)" ;;
  esac
  os_name="${PRETTY_NAME:-}"
  if [ -z "$os_name" ] && [ -r /etc/os-release ]; then
    os_name="$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '"' | head -n1)"
  fi

  mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  mem_mb=$((mem_kb / 1024))
  disk_kb="$(deps_disk_total_kb)"
  disk_gb=$((disk_kb / 1024 / 1024))
  local disk_free_kb free_mb
  disk_free_kb="$(deps_disk_free_kb)"
  free_mb=$((disk_free_kb / 1024))

  echo "HY2 AIO 运行环境自检"
  echo "系统：${os_name:-未知}  架构：${arch}"
  echo "内存：${mem_mb}MB  根分区：${disk_gb}GB（可用 ${free_mb}MB）  包管理器：${PKG_MANAGER:-未识别（无法自动补齐）}"

  if [ "$mem_mb" -gt 0 ] && [ "$mem_mb" -lt 600 ]; then
    echo "提示：内存不足 600MB，安装会自动启用 swap（512MB 小机靠它跑 Caddy + 面板）"
  fi
  if [ "$disk_gb" -gt 0 ] && [ "$disk_gb" -lt 3 ]; then
    warn "根分区只有 ${disk_gb}GB，装完客户端+证书可能不够；建议先扩容或清理，否则中途会失败"
  fi
  case "$arch" in
    *amd64*|*arm64*|*aarch64*) ;;
    *) warn "架构 ${arch} 不在官方二进制覆盖范围（只发 amd64/arm64），装不上 Hysteria/Xray" ;;
  esac
}

# 根分区总量 / 可用量（KB）。df 在不同发行版的列位略有差异，
# 这里按头行定位「Mounted on == /」那一行，取倒数第二列为可用、第三列前为总量。
deps_disk_total_kb() {
  df -Pk / 2>/dev/null | awk 'NR==2 {print $2; exit}' || echo 0
}

deps_disk_free_kb() {
  df -Pk / 2>/dev/null | awk 'NR==2 {print $4; exit}' || echo 0
}

# 小盘机器（可用 < 1.5GB）不自动装 large 档依赖：
# firewalld / fail2ban 在 Debian 上要吃掉几百 MB 并拉起常驻服务，
# 4GB 盘的小机上装它们是把用户仅剩的空间和内存挤干，得不偿失。
deps_disk_is_tight() {
  local free_kb
  free_kb="$(deps_disk_free_kb)"
  [ "${free_kb:-0}" -gt 0 ] && [ "$free_kb" -lt 1572864 ]
}

deps_pkg_name() {
  local apt="$1" rpm="$2" suse="$3"
  case "${PKG_MANAGER:-}" in
    apt) printf '%s' "$apt" ;;
    dnf|yum) printf '%s' "$rpm" ;;
    zypper) printf '%s' "$suse" ;;
    *) printf '%s' "$apt" ;;
  esac
}

# 打印一行清单：状态|命令名|包名|级别|档次|何时需要
# 状态：ok / miss
deps_scan() {
  local cmd apt rpm suse level size when pkg
  while IFS='|' read -r cmd apt rpm suse level size when; do
    [ -n "$cmd" ] || continue
    [ -n "${size:-}" ] || size="small"
    [ -n "${when:-}" ] || when="always"
    if command -v "$cmd" >/dev/null 2>&1; then
      printf 'ok|%s||%s|%s|%s\n' "$cmd" "$level" "$size" "$when"
    else
      pkg="$(deps_pkg_name "$apt" "$rpm" "$suse")"
      printf 'miss|%s|%s|%s|%s|%s\n' "$cmd" "$pkg" "$level" "$size" "$when"
    fi
  done <<EOF
$(printf '%s\n' "$DEPS_TABLE" | sed '/^[[:space:]]*$/d')
EOF
}

deps_cmd() {
  need_root deps
  local action="${1:-check}"
  case "$action" in
    check|""|show) ;;
    fix|install) ;;
    *) die "用法：hy2 deps [check|fix]" ;;
  esac

  # 只体检不需要包管理器；要修才去探测，避免只为打印而 die
  if [ -z "${PKG_MANAGER:-}" ]; then
    if command -v apt-get >/dev/null 2>&1; then
      PKG_MANAGER="apt"
    elif command -v dnf >/dev/null 2>&1; then
      PKG_MANAGER="dnf"
    elif command -v yum >/dev/null 2>&1; then
      PKG_MANAGER="yum"
    elif command -v zypper >/dev/null 2>&1; then
      PKG_MANAGER="zypper"
    fi
    export PKG_MANAGER
  fi

  local needed_missing=0 missing_core=0 fixed=0 failed=0 skipped=0
  local state cmd pkg level size when

  deps_print_device
  echo

  # 只有「此刻真的需要」的缺件才进报告。没开端口跳跃就不提 nft/iptables，
  # 没装 firewalld 就不提 firewall-cmd —— 否则小机器上每次都是一屏红字，
  # 用户以为系统有问题，实际只是我们自己在念清单。
  local deferred=()
  while IFS='|' read -r state cmd pkg level size when; do
    [ -n "$state" ] || continue
    [ "$state" = "ok" ] && continue
    if ! deps_is_required "$cmd" "$level" "$when"; then
      deferred+=("$cmd")
      continue
    fi
    if [ "$action" = "fix" ]; then
      if [ -z "$pkg" ]; then
        printf '  %-14s 缺失，且没有可自动安装的软件包\n' "$cmd"
        needed_missing=$((needed_missing + 1))
        failed=$((failed + 1))
        continue
      fi
      # 小盘机器跳过 large 档：装了会把剩余空间和内存挤干。
      # 这是「主动放弃」而不是「没修好」，所以不计入 needed_missing，
      # 否则 fix 结束还会自相矛盾地报「仍缺 1 项」。
      if [ "$size" = "large" ] && deps_disk_is_tight; then
        printf '  %-14s 缺失，可用空间不足，跳过 %s（可手动 apt install %s 自行决定）\n' \
          "$cmd" "$pkg" "$pkg"
        skipped=$((skipped + 1))
        continue
      fi
      printf '  %-14s 缺失，安装 %s ...' "$cmd" "$pkg"
      if pkg_install_quiet "$pkg" && command -v "$cmd" >/dev/null 2>&1; then
        printf ' 完成\n'
        fixed=$((fixed + 1))
      else
        printf ' 失败\n'
        needed_missing=$((needed_missing + 1))
        if [ "$level" = "core" ]; then
          missing_core=$((missing_core + 1))
        fi
        failed=$((failed + 1))
      fi
    else
      needed_missing=$((needed_missing + 1))
      if [ "$level" = "core" ]; then
        missing_core=$((missing_core + 1))
      fi
      printf '  %-14s 缺失（软件包：%s）\n' "$cmd" "$pkg"
    fi
  done <<EOF
$(deps_scan)
EOF

  echo
  if [ "$action" = "fix" ]; then
    if [ "$failed" -gt 0 ]; then
      warn "有 ${failed} 项没能自动补齐；按上面的包名手动装，或换更完整的系统镜像"
      return 1
    fi
    if [ "$fixed" -gt 0 ]; then
      log "已补装 ${fixed} 项"
    else
      log "无需补装"
    fi
    [ "$skipped" -gt 0 ] && warn "${skipped} 项因磁盘空间不足跳过（不影响当前功能）"
  fi

  # 面板二维码库不在 deps_scan 的命令清单里（它是个 JS 文件不是系统包），
  # 单独检查：缺了直接现场调 install_panel_vendor 修（GitHub 失败会走
  # jsdelivr 镜像）。以前不查这项，新装机/repair 后二维码悄悄缺失，
  # 用户扫码时才看到「二维码库没装好」（真机踩过）。
  # 面板变量来自 panel.sh;deps 可以单独 source(测试场景),未加载时跳过此检查
  # ⚠️ 别写成 ${#PANEL_VENDOR_FILES[@]:-0} —— ${#arr[@]} 后面不能接默认值,
  # bash 直接 "bad substitution" 报错;再叠 set -Eeuo pipefail 就整个安装中断。
  # (2026-11-24 新装机 v1.8.2 真机踩到:依赖自检打完就退出,装不下去)
  # 也不能直接写 ${#arr[@]}: set -u 下未定义数组会 "unbound variable",
  # 所以先用 +set 判断存在性,再取长度。
  local panel_vendor_count=0
  if [ -n "${PANEL_VENDOR_FILES+set}" ]; then
    panel_vendor_count=${#PANEL_VENDOR_FILES[@]}
  fi
  if [ "${PANEL_VENDOR_DIR:-}" = "" ] || [ "$panel_vendor_count" -eq 0 ]; then
    : # panel.sh 未加载(纯 deps 环境),跳过二维码检查
  elif [ "$action" = "fix" ] && [ ! -d "${WEB_DIR:-/var/www/hy2-aio}" ]; then
    : # 首次安装阶段面板尚未写入，稍后 write_panel 会安装二维码库
  elif [ -f "${PANEL_VENDOR_DIR}/qrcode.min.js" ]; then
    local vendor_want=""
    # SHA 来源与 install_panel_vendor 同一份清单,避免两处维护漂移
    vendor_want="${PANEL_VENDOR_FILES[0]%% *}"
    if [ -n "$vendor_want" ] && [ "$(font_sha256 "${PANEL_VENDOR_DIR}/qrcode.min.js")" != "$vendor_want" ]; then
      if [ "$action" = "fix" ]; then
        warn "二维码库校验不符（文件损坏或版本过旧）"
        install_panel_vendor 1 >/dev/null 2>&1 || true
        [ "$(font_sha256 "${PANEL_VENDOR_DIR}/qrcode.min.js" 2>/dev/null)" = "$vendor_want" ] \
          && log "二维码库已修复" \
          || warn "二维码库修复失败；不影响代理，仅面板扫码不可用（可稍后重试 sudo hy2 repair）"
      else
        warn "二维码库校验不符（执行 sudo hy2 deps fix 修复）"
      fi
    fi
  else
    if [ "$action" = "fix" ]; then
      warn "面板二维码库缺失（面板扫码不可用，代理不受影响）；尝试自动补齐..."
      install_panel_vendor 1 >/dev/null 2>&1 || true
      if [ -f "${PANEL_VENDOR_DIR}/qrcode.min.js" ]; then
        log "二维码库已补齐"
      else
        warn "二维码库补齐失败（多为国内 VPS 拉 GitHub 超时）；稍后重试 sudo hy2 repair"
      fi
    else
      warn "面板二维码库缺失（面板扫码不可用，执行 sudo hy2 deps fix 补齐）"
    fi
  fi

  if [ "$needed_missing" -eq 0 ]; then
    log "当前功能所需的依赖齐全，服务可以正常运行"
    if [ "${#deferred[@]}" -gt 0 ]; then
      echo "（另有 ${#deferred[@]} 项未启用功能才会用到，已跳过：${deferred[*]}）"
    fi
    return 0
  fi

  if [ "$missing_core" -gt 0 ]; then
    warn "缺少 ${missing_core} 项基础依赖，服务跑不起来；执行 sudo hy2 deps fix 自动补齐"
    return 1
  fi
  warn "缺少 ${needed_missing} 项当前功能要用的工具；执行 sudo hy2 deps fix 自动补齐"
  return 1
}