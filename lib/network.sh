#!/usr/bin/env bash
# network.sh - 混淆、端口与端口跳跃管理

obfs_is_enabled() {
  local raw
  raw="$(printf '%s' "${OBFS_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

set_config_env_var() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
found = False
output = []
for line in lines:
    if line.startswith(f"{key}="):
        output.append(f"{key}={value}")
        found = True
    else:
        output.append(line)
if not found:
    output.append(f"{key}={value}")
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
os.replace(temporary, path)
PY
  chown root:hy2-aio "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
}

apply_hysteria_client_settings() {
  write_rebuild_helper
  "$REBUILD_FILE"
  chown hysteria:hysteria "$HYSTERIA_CONFIG"
  chmod 0660 "$HYSTERIA_CONFIG"
  write_access_file
  if [ -f "${HY2_OFF_FILE:-/etc/hy2-aio/hy2.off}" ]; then
    log "Hysteria 已关闭，配置已写入（开启：hy2 on）"
  else
    systemctl restart hysteria-server.service
  fi
  api_post sync >/dev/null || true
}

obfs_cmd() {
  need_root obfs
  read_env
  local action="${1:-show}"
  case "$action" in
    show|status|"")
      if obfs_is_enabled; then
        echo "obfs: on (salamander)"
      else
        echo "obfs: off"
      fi
      echo "keepalive: 5s（订阅） / QUIC keepAlivePeriod: ${QUIC_KEEP_ALIVE_PERIOD:-5s}"
      ;;
    on|enable)
      set_config_env_var OBFS_ENABLED true
      export OBFS_ENABLED=true
      apply_hysteria_client_settings
      log "已开启 Salamander 混淆；请客户端更新订阅"
      ;;
    off|disable)
      set_config_env_var OBFS_ENABLED false
      export OBFS_ENABLED=false
      apply_hysteria_client_settings
      log "已关闭混淆（加密仍在）；请客户端更新订阅"
      ;;
    *)
      die "用法：hy2 obfs on|off|show"
      ;;
  esac
}

prompt_obfs_enabled() {
  local value="${HY2_OBFS:-}" answer=""
  if [ -n "$value" ]; then
    value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
    case "$value" in
      1|true|yes|on|y) printf '%s' "true"; return ;;
      0|false|no|off|n) printf '%s' "false"; return ;;
      *) die "HY2_OBFS 须为 0/1 或 true/false" ;;
    esac
  fi
  if [ "${HY2_NONINTERACTIVE:-0}" = "1" ] || [ ! -t 0 ]; then
    printf '%s' "true"
    return
  fi
  echo "  提示：开启后更隐蔽；若以后经常断线，可再执行 hy2 obfs off" >&2
  read -r -p "开启流量伪装（Salamander）？直接回车=开启 [Y/n]: " answer || true
  answer="$(printf '%s' "${answer:-Y}" | tr '[:upper:]' '[:lower:]')"
  case "$answer" in
    ""|y|yes) printf '%s' "true" ;;
    n|no) printf '%s' "false" ;;
    *)
      warn "无效输入，已默认开启"
      printf '%s' "true"
      ;;
  esac
}

# Hysteria 监听 0.0.0.0 时走 iptables 后端要求 iptables 和 ip6tables 两把都在
# （firewall_linux.go 的 iptablesBinariesForAddr 会对通配地址同时 LookPath 两个），
# 只装了 iptables 的话规则建不起来、服务直接拒绝启动，所以这里当成「不可用」。
hop_firewall_backend() {
  if command -v nft >/dev/null 2>&1; then
    printf '%s' "nft"
  elif command -v iptables >/dev/null 2>&1 && command -v ip6tables >/dev/null 2>&1; then
    printf '%s' "iptables"
  fi
}

# Hysteria 写端口重定向规则要调用 nft/iptables；两者都没有时启动会直接失败。
ensure_hop_firewall_tool() {
  [ -n "$(hop_firewall_backend)" ] && return 0
  warn "未找到可用的 nft / iptables+ip6tables，尝试安装（Hysteria 建立端口重定向需要）"
  pkg_install_quiet nftables || pkg_install_quiet iptables
  [ -n "$(hop_firewall_backend)" ] \
    || die "缺少 nft 或 iptables/ip6tables：Debian/Ubuntu 用 apt install nftables，RHEL 系用 dnf install iptables（某些精简系统要另外装 iptables-ipv6）"
}

ensure_hop_capability() {
  local caps dropin="${HYSTERIA_DROPIN_DIR:-/etc/systemd/system/hysteria-server.service.d}/hy2-capabilities.conf"
  caps="$(systemctl show hysteria-server.service -p AmbientCapabilities --value 2>/dev/null | tr '[:upper:]' '[:lower:]')"
  case "$caps" in
    *cap_net_admin*) return 0 ;;
  esac
  warn "hysteria-server 缺少 CAP_NET_ADMIN，写入 systemd drop-in 后重试"
  install -d -m 0755 "$(dirname "$dropin")"
  cat > "$dropin" <<EOF
[Service]
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
EOF
  chmod 0644 "$dropin"
  systemctl daemon-reload
  caps="$(systemctl show hysteria-server.service -p AmbientCapabilities --value 2>/dev/null | tr '[:upper:]' '[:lower:]')"
  case "$caps" in
    *cap_net_admin*) log "已授予 CAP_NET_ADMIN" ;;
    *) die "无法授予 CAP_NET_ADMIN；请检查 hysteria-server.service 的 CapabilityBoundingSet" ;;
  esac
}

hop_check_cmd() {
  read_env
  local range backend caps listen_port redirect failures=0 nft_out ipt_range ipt_out
  if ! port_hop_enabled; then
    echo "端口跳跃：off"
    echo "默认范围：$(default_hop_range)/UDP；开启：sudo hy2 hop on"
    return 0
  fi
  range="$(hop_range)"
  listen_port="${HY2_PORT:-443}"
  backend="$(hop_firewall_backend)"
  echo "端口跳跃：${range}/UDP（间隔 ${PORT_HOP_INTERVAL:-30}s）"
  echo

  if [ -n "$backend" ]; then
    log "自检 1/7 通过：防火墙工具 ${backend}"
  else
    warn "自检 1/7 失败：未找到 nft/iptables（hy2 hop on 会自动尝试安装）"
    failures=$((failures + 1))
  fi

  caps="$(systemctl show hysteria-server.service -p AmbientCapabilities --value 2>/dev/null | tr '[:upper:]' '[:lower:]')"
  case "$caps" in
    *cap_net_admin*) log "自检 2/7 通过：服务具备 CAP_NET_ADMIN" ;;
    *)
      warn "自检 2/7 失败：hysteria-server.service 缺少 CAP_NET_ADMIN"
      failures=$((failures + 1))
      ;;
  esac

  if systemctl is-active --quiet hysteria-server.service; then
    log "自检 3/7 通过：hysteria-server 运行中"
  else
    warn "自检 3/7 失败：hysteria-server 未运行（journalctl -u hysteria-server -n 80）"
    failures=$((failures + 1))
  fi

  if ss -Hlunp 2>/dev/null | awk -v p=":${listen_port}" '$4 ~ p"$" || $4 ~ p" " {found=1} END {exit !found}'; then
    log "自检 4/7 通过：监听 UDP ${listen_port}"
  else
    warn "自检 4/7 失败：未看到监听 UDP ${listen_port}"
    failures=$((failures + 1))
  fi

  redirect="$(hop_redirect_range || true)"
  if [ -z "$redirect" ]; then
    warn "自检 5/7 失败：端口范围无效，无法推导重定向区间（${range}）"
    failures=$((failures + 1))
  elif [ "$backend" = "nft" ]; then
    nft_out="$(nft list ruleset 2>/dev/null || true)"
    if printf '%s\n' "$nft_out" | grep -q "hysteria_" \
      && printf '%s\n' "$nft_out" | grep -q -- "dport ${redirect}"; then
      log "自检 5/7 通过：nft 重定向规则已存在（${redirect} → ${listen_port}）"
    else
      warn "自检 5/7 失败：没找到 nft 重定向规则（${redirect} → ${listen_port}；journalctl -u hysteria-server 查 firewall）"
      failures=$((failures + 1))
    fi
  elif [ "$backend" = "iptables" ]; then
    ipt_range="${redirect/-/:}"
    ipt_out="$( { iptables -t nat -S 2>/dev/null; ip6tables -t nat -S 2>/dev/null; } || true)"
    if printf '%s\n' "$ipt_out" | grep -q "HYSTERIA-PR-" \
      && printf '%s\n' "$ipt_out" | grep -q -- "--dport ${ipt_range}"; then
      log "自检 5/7 通过：iptables 重定向规则已存在（${redirect} → ${listen_port}）"
    else
      warn "自检 5/7 失败：没找到 iptables 重定向规则（${redirect} → ${listen_port}；iptables -t nat -S | grep HYSTERIA）"
      failures=$((failures + 1))
    fi
  else
    warn "自检 5/7 失败：没有可用的防火墙工具"
    failures=$((failures + 1))
  fi

  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    if ufw status 2>/dev/null | grep -qE "^${listen_port}/udp[[:space:]]+ALLOW"; then
      log "自检 6/7 通过：ufw 已放行 ${listen_port}/udp（重定向后只需基准端口）"
    else
      warn "自检 6/7 失败：ufw 未放行 ${listen_port}/udp"
      failures=$((failures + 1))
    fi
  elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    if firewall-cmd --query-port="${listen_port}/udp" >/dev/null 2>&1; then
      log "自检 6/7 通过：firewalld 已放行 ${listen_port}/udp"
    else
      warn "自检 6/7 失败：firewalld 未放行 ${listen_port}/udp"
      failures=$((failures + 1))
    fi
  else
    log "自检 6/7 跳过：本机未启用 ufw/firewalld"
  fi

  # 第 7 项：残留的 NAT 链。Hysteria 被秒杀时会留下 HYSTERIA-PR-/hysteria_，
  # 下次启动撞名直接 FATAL。这里只报告，不动手（改动交给 hy2 restart）。
  #
  # 判定前提：**Hysteria 正在运行时链本来就该存在**，那不是残留。
  # 早期版本只看「链是否存在」，导致服务正常时 5/7 说「规则已存在」、
  # 7/7 又说「有残留」，两条自相矛盾，把正常机器判成坏的。
  local leftovers svc_active=1
  if ! systemctl is-active --quiet hysteria-server.service 2>/dev/null; then
    svc_active=0
  fi
  leftovers="$(hysteria_nat_leftovers 2>/dev/null || true)"
  if [ "$svc_active" = "1" ]; then
    log "自检 7/7 跳过：Hysteria 正在运行，重定向链属正常状态"
    if [ -n "$leftovers" ]; then
      log "  （运行中的链：$(printf '%s' "$leftovers" | tr '
' ' ')）"
    fi
  elif [ -z "$leftovers" ]; then
    log "自检 7/7 通过：服务已停止且没有残留的 NAT 重定向链"
  else
    warn "自检 7/7 失败：服务已停止但仍有残留重定向规则（下次启动会「链已存在」）"
    printf '%s\n' "$leftovers" | sed 's/^/    • /' >&2
    warn "修复：sudo hy2 restart（会先清理再启动）"
    failures=$((failures + 1))
  fi

  echo
  echo "云控制台安全组必须放行：UDP ${range}（入站，0.0.0.0/0）"
  echo "外网验收：手机蜂窝网络导入订阅，连续断开重连 5 次都成功才算可用。"
  if [ "$failures" -eq 0 ]; then
    log "本机自检全部通过"
    return 0
  fi
  warn "本机自检有 ${failures} 项未通过，先修掉再让用户用"
  return 1
}

# port_cmd - 查看与修改 HY2 / VLESS 端口
#
# 背景：端口经常需要换 —— 运营商 DPI 会针对某些端口做选择性干扰
# （实测 8443 的 TLS 握手被掐、2083 正常）。而原来改端口只能手工
# sed config.env + 手动跑 rebuild，改完还容易遇到「restart 不生效」的坑。
#
# 这条命令统一处理：
#   校验端口布局（不能与面板/统计/后端冲突、不能被占用）
#   写 config.env
#   触发配置重建（hysteria + xray）
#   重启服务（HY2 走 stop→clean→start，防 NAT 链残留）
#   提示用户重新导入订阅
port_cmd() {
  need_root port
  read_env
  local target="${1:-show}" value="${2:-}"

  case "$target" in
    show|status|"")
      local hop_info=""
      if command -v port_hop_enabled >/dev/null 2>&1 && port_hop_enabled; then
        hop_info="（端口跳跃 $(hop_range)，间隔 ${PORT_HOP_INTERVAL:-30}s）"
      fi
      echo "HY2 UDP：${HY2_PORT:-443} ${hop_info}"
      echo "VLESS TCP：${XRAY_PORT:-}（实际监听以 ss 为准）"
      echo "面板 HTTPS：${PANEL_PORT:-443} / 统计：${STATS_PORT:-9999}"
      echo
      echo "修改："
      echo "  sudo hy2 port hy2 8443          # HY2 单端口（或 范围 如 8443-9443 开启跳跃）"
      echo "  sudo hy2 port vless 2083        # VLESS 端口"
      echo "改动会自动重建配置并重启服务，在线用户会短暂断开。"
      echo "改完需要【重新导入订阅】。"
      return 0
      ;;
    hy2|vless)
      ;;
    *)
      die "未知目标：$target（可用：hy2 / vless / show）"
      ;;
  esac

  local key
  case "$target" in
    hy2)   key="HY2_PORT" ;;
    vless) key="XRAY_PORT" ;;
  esac

  [ -n "$value" ] || die "缺少端口值。用法：sudo hy2 port $target <端口或范围>"

  # ---- 校验 ----
  local new_port="$value" new_hi=""
  if [ "$target" = "vless" ]; then
    port_number_is_valid "$new_port" || die "端口无效：$new_port（必须是 1-65535 的整数）"
  else
    # HY2 允许范围（端口跳跃），起点可以是任意新端口，不要求等于旧 HY2_PORT
    if [[ "$new_port" == *-* ]]; then
      local r_start r_end
      [[ "$new_port" =~ ^([0-9]{1,5})-([0-9]{1,5})$ ]] \
        || die "端口范围无效：$new_port（如 8443-9443，须在 1-65535 内且起点<终点、跨度 ≤2000）"
      r_start="${BASH_REMATCH[1]}"
      r_end="${BASH_REMATCH[2]}"
      port_number_is_valid "$r_start" && port_number_is_valid "$r_end" \
        && [ $((10#$r_end)) -gt $((10#$r_start)) ] \
        && [ $((10#$r_end - 10#$r_start)) -le 2000 ] \
        || die "端口范围无效：$new_port（如 8443-9443，须在 1-65535 内且起点<终点、跨度 ≤2000）"
      new_port=$((10#$r_start))
      new_hi=$((10#$r_end))
      value="${new_port}-${new_hi}"
    else
      port_number_is_valid "$new_port" || die "端口无效：$new_port"
    fi
  fi

  # 与其他角色的端口冲突
  local panel_port="${PANEL_PORT:-443}" stats_port="${STATS_PORT:-9999}"
  for p in "$panel_port" "$stats_port" "$BACKEND_PORT"; do
    [ "$new_port" = "$p" ] && die "端口冲突：$new_port 与内部端口 $p 相同"
  done

  # HY2 端口跳跃的 UDP 范围与 VLESS 的 TCP 端口必须错开。
  # 虽然 UDP/TCP 同号在系统层面不冲突，但：
  #   - 客户端配置里两个节点端口撞车极易配错
  #   - 端口跳跃的 NAT 规则会 REDIRECT 整段 dport，范围含 VLESS 端口时
  #     防火墙规则多了难以排查
  # 更重要的是：把 VLESS 换到 HY2 范围里，HY2 的 REDIRECT 规则会把它算进
  # 自己管辖的段（实测就是这么踩到的隐藏 bug）。
  local hy2_lo="${HY2_PORT:-}" hy2_hi=""
  local hop_rng=""
  # 只有端口跳跃【启用时】才把范围算进来 —— 关闭时 PORT_HOP_RANGE 可能
  # 还留着历史值（或已清空），拿它判定会误拦（实测踩过，hop off 后
  # 仍报「落在范围内」）。
  if command -v port_hop_enabled >/dev/null 2>&1 && port_hop_enabled; then
    hop_rng="$(hop_range 2>/dev/null || true)"
    [ -n "$hop_rng" ] || hop_rng="${PORT_HOP_RANGE:-}"
  fi
  if [ -n "$hop_rng" ]; then
    hy2_lo="${hop_rng%%-*}"
    hy2_hi="${hop_rng##*-}"
  fi
  # 单端口情况也检查（PORT_HOP_RANGE 可能只写一个数字）
  if [ -n "$hy2_hi" ] && [ "$hy2_hi" = "$hy2_lo" ]; then
    hy2_hi="$hy2_lo"
  fi
  if [ "$target" = "vless" ] && [ -n "$hy2_hi" ]; then
    if [ "$new_port" -ge "$hy2_lo" ] && [ "$new_port" -le "$hy2_hi" ]; then
      die "端口冲突：VLESS $new_port 落在 HY2 端口跳跃范围 ${hy2_lo}-${hy2_hi}（UDP）内。
换一个范围外的端口，例如：sudo hy2 port vless $((hy2_hi + 1))"
    fi
  fi
  if [ "$target" = "hy2" ] && [ -n "$new_hi" ]; then
    local vless_now="${XRAY_PORT:-}"
    if [ -n "$vless_now" ] && [ "$vless_now" -ge "$new_port" ] && [ "$vless_now" -le "$new_hi" ]; then
      die "端口冲突：HY2 范围 $value 包含当前 VLESS 端口 $vless_now。
先把 VLESS 挪出该范围：sudo hy2 port vless $((new_hi + 1))"
    fi
  fi

  case "$target" in
    hy2)
      # HY2 是 UDP；VLESS 是 TCP，理论可同号但容易混淆，禁止相同
      [ "$new_port" = "${XRAY_PORT:-}" ] && die "端口冲突：HY2 与 VLESS 不能同为 $new_port"
      ;;
    vless)
      [ "$new_port" = "${HY2_PORT:-}" ] && die "端口冲突：VLESS 与 HY2 不能同为 $new_port"
      ;;
  esac

  # 与现有监听冲突。排除「自己当前就占着这个口」的情况 ——
  # 重复执行同一命令（比如中断后重试）不该报错，直接走幂等路径。
  local port_owner=""
  # 从 ss 的 users:(("xray",pid=123,fd=3)) 里抠出进程名。
  # 早先用 grep -oE '[a-z0-9-]+\)$' 是错的：ss 行尾有大量空白、
  # 且以 )) 收尾，那个正则永远匹配不上 → grep 返回 1 →
  # pipefail + set -e 让整个函数静默退出：面板显示"成功"，
  # 实际什么都没改。这是真机上踩到的 bug。
  port_owner="$(ss -Hlntp 2>/dev/null | awk -v p=":$new_port" '$4 ~ p"$" { s=$NF; if (match(s, /[(][(]"/)) { s=substr(s, RSTART+3); if (match(s, /"/)) { print substr(s, 1, RSTART-1); exit } } }' || true)"
  if [ "$target" = "vless" ] && tcp_port_is_used "$new_port"; then
    case "$port_owner" in
      xray) log "TCP $new_port 已由 Xray 监听（重复操作，走幂等路径）" ;;
      *) die "TCP $new_port 已被 $port_owner 占用（ss -lntp | grep $new_port）" ;;
    esac
  fi
  if [ "$target" = "hy2" ] && port_is_used "$new_port"; then
    port_owner="$(ss -Hlunp 2>/dev/null | awk -v p=":$new_port" '$4 ~ p"$" { s=$NF; if (match(s, /[(][(]"/)) { s=substr(s, RSTART+3); if (match(s, /"/)) { print substr(s, 1, RSTART-1); exit } } }' || true)"
    case "$port_owner" in
      hysteria) log "UDP $new_port 已由 Hysteria 监听（重复操作，走幂等路径）" ;;
      "") ;;   # 端口跳跃范围被 NAT 转发占着，没有监听进程，不算冲突
      *) die "UDP $new_port 已被 $port_owner 占用（ss -lunp | grep $new_port）" ;;
    esac
  fi

  # ---- 写入 ----
  # 「无变化」判定不能只看 config.env —— 上次操作可能 env 写了但重建没
  # 跑完（中断/断连），此时 env 已是新值、实际配置还是旧的。要比对
  # xray.json 里真实生效的端口，不一致就照常走重建。
  local old_value current_actual=""
  case "$target" in
    hy2)   old_value="${HY2_PORT:-}" ;;
    vless) old_value="${XRAY_PORT:-}" ;;
  esac
  if [ "$target" = "vless" ] && [ -f "${XRAY_CONFIG:-/etc/hy2-aio/xray.json}" ]; then
    current_actual="$(python3 - "$XRAY_CONFIG" <<'PY'
import json, sys
try:
    inbounds = json.load(open(sys.argv[1], encoding="utf-8")).get("inbounds", [])
    ports = {str(i.get("port")) for i in inbounds if i.get("port")}
    print(next(iter(ports)) if len(ports) == 1 else "")
except Exception:
    print("")
PY
)"
    if [ "$new_port" = "$old_value" ] && [ "$current_actual" != "$new_port" ]; then
      warn "config.env 已是 $new_port 但实际监听配置是 ${current_actual:-未知}（上次操作未完成），继续重建"
    fi
  fi
  local unchanged=0
  if [ "$target" = "vless" ]; then
    if [ "$new_port" = "$old_value" ] && [ "$current_actual" = "$new_port" ]; then
      unchanged=1
    fi
  elif [ -n "$new_hi" ]; then
    if port_hop_enabled && [ "$new_port" = "$old_value" ] && [ "$(hop_range 2>/dev/null || true)" = "$value" ]; then
      unchanged=1
    fi
  else
    if ! port_hop_enabled && [ "$new_port" = "$old_value" ]; then
      unchanged=1
    fi
  fi
  if [ "$unchanged" -eq 1 ]; then
    log "端口未变化（$target = $value），无需操作"
    return 0
  fi

  log "回滚快照：$(snapshot_before_change)"
  if [ "$target" = "hy2" ] && [ -n "$new_hi" ]; then
    # 范围形式：更新基准端口并开启端口跳跃
    set_config_env_var HY2_PORT "$new_port"
    set_config_env_var PORT_HOP_RANGE "$value"
    set_config_env_var PORT_HOP_ENABLED true
  elif [ "$target" = "hy2" ]; then
    # 单端口形式：关闭端口跳跃并清旧范围，防止 rebuild_config.py 因旧范围起点不匹配而失败
    set_config_env_var HY2_PORT "$new_port"
    set_config_env_var PORT_HOP_ENABLED false
    set_config_env_var PORT_HOP_RANGE ""
  else
    set_config_env_var "$key" "$new_port"
  fi

  # ---- 重建 + 重启 ----
  read_env
  # 注意：不要在这里 systemctl restart hy2-aio.service！
  #
  # 面板点"应用"时，root 侧的请求正是【由 hy2-aio 后端进程发起】的
  # （后端写 cmd 文件 → path unit → control 脚本 → 这里）。此时重启
  # hy2-aio 等于把正在处理该请求的进程杀掉 → Caddy 拿到 502 →
  # 用户看到第一次点失败、第二次才成功（真机实测 502/200 交替）。
  #
  # 而且这一步本就是多余的：后端的 load_env() 每次都从磁盘重读
  # config.env，没有任何内存缓存，无需重启就能看到新端口。
  # config.env 已在上面写好了，直接重建即可。
  log "重建配置..."
  if [ -x "$REBUILD_FILE" ]; then
    "$REBUILD_FILE" || die "Hysteria 配置重建失败"
  fi
  if [ -x "$XRAY_REBUILD_FILE" ]; then
    "$XRAY_REBUILD_FILE" || die "Xray 配置重建失败"
  fi
  chown hysteria:hysteria "$HYSTERIA_CONFIG" 2>/dev/null || true
  chmod 0660 "$HYSTERIA_CONFIG" 2>/dev/null || true
  api_post sync >/dev/null 2>&1 || warn "sync 刷新失败，将在下次采集同步"

  # 若本机启用了 ufw / firewalld，同步放行新端口
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    if [ "$target" = "hy2" ]; then
      ufw allow "${new_port}/udp" >/dev/null 2>&1 || true
    else
      ufw allow "${new_port}/tcp" >/dev/null 2>&1 || true
    fi
  elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    if [ "$target" = "hy2" ]; then
      firewall-cmd --permanent --add-port="${new_port}/udp" >/dev/null 2>&1 || true
    else
      firewall-cmd --permanent --add-port="${new_port}/tcp" >/dev/null 2>&1 || true
    fi
    firewall-cmd --reload >/dev/null 2>&1 || true
  fi

  log "重启内核（在线用户会短暂断开）..."
  if ! hy2_is_off; then
    systemctl stop hysteria-server.service 2>/dev/null || true
    clean_hysteria_nat_rules >/dev/null 2>&1 || true
    systemctl start hysteria-server.service
    wait_hysteria_stats_api
  fi
  if ! xray_is_off && hy2_has_enabled_user 2>/dev/null; then
    restart_hy2_xray_or_die
  fi

  echo
  log "端口已更新：$target = $value"
  warn "订阅内容已变化，请在客户端【重新导入订阅】"
}

hop_cmd() {
  need_root hop
  read_env
  local action="${1:-show}" value previous_range="" apply_failed=0
  case "$action" in
    show|status|"")
      if port_hop_enabled; then
        echo "端口跳跃：on"
        echo "范围：$(hop_range)/UDP（间隔 ${PORT_HOP_INTERVAL:-30}s）"
        echo "订阅：Clash 写入 ports + hop-interval；直链端口位写作 $(hop_range)"
        echo "云安全组需放行：UDP $(hop_range)"
        echo "自检：sudo hy2 hop check"
      else
        echo "端口跳跃：off"
        echo "默认范围：$(default_hop_range)/UDP"
        echo "开启：sudo hy2 hop on（会重启 Hysteria，在线用户会短暂断开）"
      fi
      ;;
    check)
      hop_check_cmd
      ;;
    on|enable)
      if [ -f "${HY2_OFF_FILE:-/etc/hy2-aio/hy2.off}" ]; then
        die "Hysteria 当前处于关闭状态，先执行：sudo hy2 on"
      fi
      ensure_hop_firewall_tool
      ensure_hop_capability
      if [ -z "${PORT_HOP_RANGE:-}" ]; then
        value="$(default_hop_range)" \
          || die "代理端口 ${HY2_PORT:-443} 已经到 65535，往后没有可用端口可跳。先改小代理端口（hy2 install 时选个更低的，或手动改 config.env 的 HY2_PORT）再开启端口跳跃"
        set_config_env_var PORT_HOP_RANGE "$value"
        export PORT_HOP_RANGE="$value"
      fi
      if [ -z "${PORT_HOP_INTERVAL:-}" ]; then
        set_config_env_var PORT_HOP_INTERVAL 30
        export PORT_HOP_INTERVAL=30
      fi
      validate_hop_range "$(hop_range)"
      validate_hop_interval "$PORT_HOP_INTERVAL"
      set_config_env_var PORT_HOP_ENABLED true
      export PORT_HOP_ENABLED=true
      # 必须用 || true 兜住：apply_hysteria_client_settings 内部 systemctl restart
      # 失败会返回非零，脚本开着 set -Eeuo pipefail 会就地退出，
      # 下面的回滚判断根本执行不到，Hysteria 会永远停在起不来的状态。
      apply_failed=0
      if ! apply_hysteria_client_settings; then
        warn "Hysteria 重启失败"
        apply_failed=1
      fi
      sleep 2
      # apply_failed 也要回滚：重启失败时旧配置可能还在跑，is-active 会骗人说「活着」，
      # 但新配置压根没生效，端口跳跃实际是关的，配置里却写着 on。
      if [ "$apply_failed" -eq 1 ] || ! systemctl is-active --quiet hysteria-server.service; then
        warn "Hysteria 没能带着端口范围启动，自动回滚到单端口"
        journalctl -u hysteria-server.service --no-pager -n 40 >&2 || true
        set_config_env_var PORT_HOP_ENABLED false
        export PORT_HOP_ENABLED=false
        apply_hysteria_client_settings || true
        die "端口跳跃启用失败，已回滚；请查看上方日志"
      fi
      if ! hop_check_cmd; then
        warn "自检未全部通过；最可能是云安全组还没放行 UDP $(hop_range)"
      fi
      ;;
    off|disable)
      set_config_env_var PORT_HOP_ENABLED false
      export PORT_HOP_ENABLED=false
      # 关也兜住：配置已经写成 off，服务没重启成功的话实际还在范围监听，
      # 用户会以为关了其实没关。这里报错但保留 off（宁可显示关闭也别谎报）。
      if ! apply_hysteria_client_settings; then
        warn "端口跳跃配置已关闭，但 Hysteria 重启失败；执行 sudo hy2 restart 让单端口生效"
      else
        log "已关闭端口跳跃，恢复单端口 ${HY2_PORT:-443}/UDP；请客户端更新订阅"
      fi
      ;;
    range)
      value="${2:-}"
      [ -n "$value" ] \
        || die "用法：hy2 hop range ${HY2_PORT:-8443}-$((10#${HY2_PORT:-8443} + 1000))"
      validate_hop_range "$value"
      previous_range="${PORT_HOP_RANGE:-}"
      set_config_env_var PORT_HOP_RANGE "$value"
      export PORT_HOP_RANGE="$value"
      if port_hop_enabled; then
        # 同 hop on：重启失败不能让 set -e 掐断回滚路径。
        apply_failed=0
        if ! apply_hysteria_client_settings; then
          warn "Hysteria 重启失败"
          apply_failed=1
        fi
        if [ ! -f "${HY2_OFF_FILE:-/etc/hy2-aio/hy2.off}" ]; then
          sleep 2
          if [ "$apply_failed" -eq 1 ] || ! systemctl is-active --quiet hysteria-server.service; then
            warn "Hysteria 没能带着新范围启动，回滚到 ${previous_range:-默认范围}"
            journalctl -u hysteria-server.service --no-pager -n 40 >&2 || true
            if [ -n "$previous_range" ]; then
              set_config_env_var PORT_HOP_RANGE "$previous_range"
            fi
            export PORT_HOP_RANGE="$previous_range"
            apply_hysteria_client_settings || true
            die "新范围启用失败，已回滚；请查看上方日志"
          fi
          hop_check_cmd || true
        fi
        log "范围已更新为 ${value}；请客户端更新订阅"
      else
        log "范围已保存为 ${value}（端口跳跃当前关闭）"
      fi
      ;;
    interval)
      value="${2:-}"
      [ -n "$value" ] || die "用法：hy2 hop interval 30"
      validate_hop_interval "$value"
      set_config_env_var PORT_HOP_INTERVAL "$value"
      export PORT_HOP_INTERVAL="$value"
      log "跳跃间隔已更新为 ${value}s；订阅下次刷新即生效（无需重启）"
      ;;
    *)
      die "用法：hy2 hop show|on|off|check|range <开始-结束>|interval <秒>"
      ;;
  esac
}
