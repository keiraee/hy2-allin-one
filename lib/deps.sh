#!/usr/bin/env bash
# deps.sh - 运行环境自检：识别当前机器缺什么，并按发行版自动补齐
#
# 面向的正是「小机器、精简镜像、刚重装的系统」：这类机器经常缺 python3、
# 少 jq、没有 ss，甚至把 iptables 装了却没 ip6tables。等用户在 install
# 半途撞见 `command not found` 再去猜，成本比提前自检高得多。
#
# 两个入口：
#   hy2 deps       只体检，不改系统（退出码 0 = 全都齐了）
#   hy2 deps fix   缺什么装什么（装不上的列出来，仍不阻断已经能跑的功能）

# 依赖清单：每行由 5 段组成，用 | 分隔
#   命令名 | 包名(apt) | 包名(rpm) | 包名(zypper) | 必需级别
# 必需级别：core = 缺了主功能直接不可用；optional = 缺了只影响某块功能
# 包名留空表示「没有对应软件包，只能靠别的方式装」。
DEPS_TABLE='
python3|python3|python3|python3|core
curl|curl|curl|curl|core
tar|tar|tar|tar|core
gzip|gzip|gzip|gzip|core
openssl|openssl|openssl|openssl|core
awk|gawk|gawk|gawk|core
grep|grep|grep|grep|core
sed|sed|sed|sed|core
jq|jq|jq|jq|optional
ss|iproute2|iproute|iproute2|optional
ip|iproute2|iproute|iproute2|optional
flock|util-linux|util-linux|util-linux|optional
nft|nftables|nftables|nftables|optional
iptables|iptables|iptables|iptables|optional
ip6tables|iptables|iptables|iptables|optional
ufw|ufw|ufw|ufw|optional
firewall-cmd|firewalld|firewalld|firewalld|optional
fail2ban-client|fail2ban|fail2ban|fail2ban|optional
'

# 每个命令在「这台机器上到底重不重要」，取决于当前配置：
# 不在启用的功能链路上就只提示、不报缺。
deps_is_required() {
  local cmd="$1" level="$2"
  [ "$level" = "core" ] && return 0
  case "$cmd" in
    nft|iptables|ip6tables)
      # 只有开了端口跳跃才真的要重定向规则
      if declare -F port_hop_enabled >/dev/null 2>&1 && port_hop_enabled; then
        return 0
      fi
      return 1
      ;;
    ufw|firewall-cmd)
      # 本机防火墙在跑才需要对应的放行命令
      if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
        return 0
      fi
      if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
        return 0
      fi
      return 1
      ;;
    fail2ban-client)
      # 面板登录保护用；只有已经装了 fail2ban 才要求客户端在
      [ -d /etc/fail2ban ] && return 0
      return 1
      ;;
    ss|ip|flock)
      return 0
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
  disk_kb="$(df -Pk / 2>/dev/null | awk 'NR==2 {print $2}' || echo 0)"
  disk_gb=$((disk_kb / 1024 / 1024))

  echo "HY2 AIO 运行环境自检"
  echo "系统：${os_name:-未知}  架构：${arch}"
  echo "内存：${mem_mb}MB  根分区：${disk_gb}GB  包管理器：${PKG_MANAGER:-未识别（无法自动补齐）}"

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

deps_pkg_name() {
  local apt="$1" rpm="$2" suse="$3"
  case "${PKG_MANAGER:-}" in
    apt) printf '%s' "$apt" ;;
    dnf|yum) printf '%s' "$rpm" ;;
    zypper) printf '%s' "$suse" ;;
    *) printf '%s' "$apt" ;;
  esac
}

# 打印一行清单：状态|命令名|包名|级别
# 状态：ok / miss
deps_scan() {
  local line cmd apt rpm suse level pkg
  while IFS='|' read -r cmd apt rpm suse level; do
    [ -n "$cmd" ] || continue
    if command -v "$cmd" >/dev/null 2>&1; then
      printf 'ok|%s||%s\n' "$cmd" "$level"
    else
      pkg="$(deps_pkg_name "$apt" "$rpm" "$suse")"
      printf 'miss|%s|%s|%s\n' "$cmd" "$pkg" "$level"
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

  local found_missing=0 missing_core=0 fixed=0 failed=0
  local state cmd pkg level

  deps_print_device
  echo

  while IFS='|' read -r state cmd pkg level; do
    [ -n "$state" ] || continue
    if [ "$state" = "ok" ]; then
      continue
    fi
    found_missing=$((found_missing + 1))
    if ! deps_is_required "$cmd" "$level"; then
      # 缺但当前用不到：只在 fix 时顺带提醒，不干扰体检结论
      printf '  %-16s %s\n' "$cmd" "缺失（当前功能未用到，可忽略）"
      continue
    fi
    if [ "$level" = "core" ]; then
      missing_core=$((missing_core + 1))
    fi

    if [ "$action" = "fix" ]; then
      if [ -z "$pkg" ]; then
        printf '  %-16s %s\n' "$cmd" "缺失，且没有可自动安装的软件包名"
        failed=$((failed + 1))
        continue
      fi
      printf '  %-16s %s' "$cmd" "缺失，安装 $pkg ..."
      if pkg_install_quiet "$pkg" && command -v "$cmd" >/dev/null 2>&1; then
        printf ' 完成\n'
        fixed=$((fixed + 1))
      else
        printf ' 失败\n'
        failed=$((failed + 1))
      fi
    else
      printf '  %-16s %s\n' "$cmd" "缺失（软件包：$pkg）"
    fi
  done <<EOF
$(deps_scan)
EOF

  echo
  if [ "$found_missing" -eq 0 ]; then
    log "依赖齐全，可以直接使用"
    return 0
  fi

  if [ "$action" = "fix" ]; then
    if [ "$failed" -gt 0 ]; then
      warn "有 ${failed} 项没能自动补齐；按上面的包名手动装，或换更完整的系统镜像"
      return 1
    fi
    log "已补装 ${fixed} 项，依赖自检通过"
    return 0
  fi

  # check 模式：必需项缺失才返回非零
  if [ "$missing_core" -gt 0 ]; then
    warn "缺少 ${missing_core} 项基础依赖；执行 sudo hy2 deps fix 自动补齐"
    return 1
  fi
  warn "有 ${found_missing} 项可选工具缺失；执行 sudo hy2 deps fix 一并补上"
  return 0
}