# HY2 AIO v2.1.1

一键部署 Hysteria 2 + VLESS+Reality + 多用户订阅 + 轻量 Web 面板（512MB 小机友好）。

**稳定版**见 [Releases](https://github.com/keiraee/hy2-allin-one/releases)（含版本说明与变更记录）。  
想先试用仓库 `main` 上还没发版的功能，见下方 [试用 main 开发版](#试用-main-开发版)。

## 快速开始（新机器安装）

当前版本：**v2.1.1**

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v2.1.1/hy2.sh -o hy2.sh
sudo bash hy2.sh install
```

按中文提示回车即可（公网 IP → 代理端口 → 面板端口 → 用户数 → 流量单位+数值 → 域名/伪装）。一路回车用推荐默认值（流量默认 1 TB，可选 MB / GB / TB / 无限）。

安装完看这两条：

```bash
hy2 panel     # 面板地址与登录账号
hy2 show      # 订阅链接 / 节点信息
```

## 已安装 · 升级

**只要一条命令**（`upgrade` 更新模块和配置，`restart` 让内核真正生效 —— 两个必须成对）：

```bash
sudo hy2 upgrade && sudo hy2 restart
```

升级前会自动打回滚快照（`/var/lib/hy2-aio-rollbacks/`，保留最新 10 份）。日志里看 **上次哈希 / 本次哈希** 是否不同 —— 不同才说明模块真的换了。

升级后**客户端要重新导入订阅**（分流规则、节点 TLS 参数都可能变）：

- Clash / ClashMetaForAndroid：配置 → 更新订阅
- sing-box：更新订阅
- v2rayNG：更新订阅（分流需在 App 内选「绕过大陆」预设）

### 想跟仓库最新提交（main 开发版）

```bash
sudo HY2_REPO_REF=main hy2 upgrade && sudo hy2 restart
```

`HY2_REPO_REF=main` 会写进 `config.env` 的 `HY2_TRACK_REF`，之后普通 `hy2 upgrade` 就一直跟 main，不会被后续正式版 tag 带跑。

### 已装机器还是老版本、升不上去

如果 `hy2 upgrade` 一直显示「已是 vX.Y.Z，提交未变化」，说明它钉在旧 tag 轨道上。用新引导脚本强制切轨道：

```bash
curl -fsSL "https://raw.githubusercontent.com/keiraee/hy2-allin-one/v2.1.1/hy2.sh?nocache=$(date +%s)" -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh upgrade && sudo hy2 restart
```

## 试用 main 开发版

`main` 是仓库最新提交，**不是 Release**，可能比当前正式版多功能，也可能还不稳定。第一次必须带 `HY2_REPO_REF=main`，本机会写入 `HY2_TRACK_REF=main`；之后普通 `hy2 upgrade && hy2 restart` 会继续跟 `main`，不会被后续正式版 tag 带跑。升级会先向 GitHub API 解析当前 commit，再按 SHA 下载 `SHA256SUMS` 和模块，避免 `raw.githubusercontent.com/main/` 把旧校验文件缓存住、面板不刷新。日志会打印 **上次哈希** 和 **本次哈希**（`SHA256SUMS` 指纹，main 轨道还会带提交短号）；两者不同才说明模块真的换成新文件。

已安装，强制切到 / 更新 `main`：

```bash
HY2_REPO_REF=main hy2 upgrade && hy2 restart
```

本机还没有 `hy2`，或本机 `hy2` 仍按「同版本就跳过」、升不到已移动的 tag / `main`：

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/main/hy2.sh -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh upgrade && hy2 restart
```

若升级日志没有 `钉住提交`、或面板仍是旧界面，说明 `main` 的 raw 缓存还没刷新。改用当前 commit 拉引导脚本：

```bash
sha=$(curl -fsSL https://api.github.com/repos/keiraee/hy2-allin-one/commits/main | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])')
curl -fsSL "https://raw.githubusercontent.com/keiraee/hy2-allin-one/${sha}/hy2.sh" -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh upgrade && hy2 restart
```

全新安装也直接用 `main`：

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/main/hy2.sh -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh install
```

记住轨道之后，日常更新：

```bash
hy2 upgrade && hy2 restart
```

切回 GitHub 正式版：

```bash
HY2_REPO_REF=latest hy2 upgrade && hy2 restart
```

## 使用方法

### 交互菜单

```bash
sudo hy2
```

### 命令模式

```bash
sudo hy2 status              # 查看状态
sudo hy2 show                # 显示账号
sudo hy2 panel               # 查看面板账号和密码
sudo hy2 sync                # 同步数据
sudo hy2 mode                # 速率模式菜单
sudo hy2 mode show           # 显示当前模式
sudo hy2 users               # 用户列表
sudo hy2 add-user <用户名>   # 添加用户
sudo hy2 remove-user <用户名> # 删除用户
sudo hy2 rotate-user <用户名> # 轮换密钥
sudo hy2 note <用户名> [备注] # 设置设备备注（留空清除）
sudo hy2 disable <用户名>    # 禁用用户
sudo hy2 enable <用户名>     # 启用用户
sudo hy2 on                  # 开启 Hysteria
sudo hy2 off                 # 关闭 Hysteria
sudo hy2 backup              # 备份
sudo hy2 logs [行数]         # 查看日志
sudo hy2 restart             # 重启服务
sudo hy2 cert                # 重新申请面板/订阅 HTTPS 证书
sudo hy2 update              # 更新 Hysteria 内核
sudo hy2 update-xray         # 更新 Xray 内核
sudo hy2 uninstall           # 完全卸载（服务、组件、配置、数据全清，不留残留）
sudo hy2 repair              # 修复/升级
sudo hy2 obfs show           # 查看混淆状态
sudo hy2 obfs on|off         # 开启/关闭混淆（服务端+订阅+直链同步）
```

## 无人值守安装

```bash
sudo HY2_NONINTERACTIVE=1 HY2_USERS=5 HY2_TOTAL_TB=1 bash hy2.sh install
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HY2_PUBLIC_IP` | 手动指定公网 IPv4 | 自动检测 |
| `HY2_INTERFACE` | 手动指定网卡 | 自动检测 |
| `HY2_DOMAIN` | 自定义域名 | `{ip}.sslip.io` |
| `HY2_USERS` | 用户数量 | 5 |
| `HY2_TOTAL_UNIT` | 流量单位 `mb/gb/tb/unlimited` | 向导选择（回车=tb） |
| `HY2_TOTAL_VALUE` | 流量数值（配合 UNIT，可小数） | 1 |
| `HY2_TOTAL_TB` | 兼容旧变量：十进制 TB | 1 |
| `HY2_TOTAL_BYTES` | 直接指定字节数；`0` = 无限流量 | 按单位换算 |
| `HY2_PANEL_USER` | 面板用户名 | admin |
| `HY2_PANEL_PASS` | 面板密码 | 随机生成 |
| `HY2_PANEL_PATH` | 面板路径 | 随机生成 |
| `HY2_SNI` | 客户端 SNI | www.amazon.sg |
| `HY2_OBFS` | Salamander 混淆 `0/1` | `1`（开） |
| `HY2_PORT` | Hysteria UDP 端口 | 安装向导默认 `8443` |
| `HY2_PORT_HOP` | 安装时启用端口跳跃 `0/1` | `0`（关） |
| `HY2_PORT_HOP_RANGE` | 端口跳跃范围（必须从 `HY2_PORT` 开始，跨度 ≤2000） | `HY2_PORT` 至 `HY2_PORT+1000` |
| `HY2_PORT_HOP_INTERVAL` | 客户端换端口间隔（秒） | 30 |
| `XRAY_PORT` | VLESS+Reality TCP 端口 | 默认与 `HY2_PORT` 相同 |
| `HY2_BACKUP_DAYS` | 备份保留天数 | 14 |
| `HY2_RATE_LIMIT_SUBSCRIPTION` | 订阅 `/s/` 每 IP 每分钟上限 | 30 |
| `HY2_RATE_LIMIT_API` | 面板 API 每 IP 每分钟上限 | 120 |
| `HY2_REPO_REF` | 模块 Git ref；`upgrade` 空值=已记住的 `HY2_TRACK_REF` 或 latest | install 默认 `v2.1.1` |
| `HY2_CLIENT_INSECURE` | 客户端 skip-cert-verify | sslip/IP 默认 true |
| `COUNTRY_CODE` | 节点名国旗（ISO 码如 `SG`）；留空=按服务器 IP 自动识别 | 自动识别 |
| `HYSTERIA_VERSION` | Hysteria 版本 | `v2.12.1` |
| `XRAY_VERSION` | Xray-core 版本 | `v26.3.27` |
| `CADDY_VERSION` | Caddy 回退安装版本 | `v2.11.4` |

## 目录结构

```
hy2-allin-one/
├── hy2.sh              # 入口脚本
├── SHA256SUMS          # 模块完整性校验
├── lib/                # 功能模块
│   ├── core.sh         # 基础函数
│   ├── install.sh      # 安装依赖
│   ├── config.sh       # 配置生成
│   ├── panel.sh        # Web 面板
│   ├── user.sh         # 用户管理
│   ├── cert.sh         # 证书管理
│   ├── access.sh       # 访问文件
│   ├── backup.sh       # 备份恢复
│   ├── mode.sh         # 速率模式
│   └── backend.sh      # 后端服务
└── bin/
    └── hy2.sh          # 系统命令入口
```

## 说明

- **Clash 订阅**默认 `mode: rule`（国内直连、其余走代理）及 `keepalive: 5s`；同一订阅里有 **HY2** 和 **VLESS+Reality** 两个节点，Clash 里手动选择（不是自动 fallback）。服务端写入 QUIC `keepAlivePeriod: 5s`、`maxIdleTimeout: 120s`。
- **VLESS+Reality** 用官方 [Xray-core](https://github.com/XTLS/Xray-core)（Vision），伪装站默认 `www.apple.com:443`。默认与 HY2 同端口号：HY2 走 UDP，VLESS 走 TCP。`hy2 off` 只关 Hysteria，Xray 继续跑。
- **复制直链**一次给出两行：`hysteria2://` 和 `vless://`。
- **混淆默认开启**；不稳时可 `sudo hy2 obfs off` 后让客户端更新订阅（关闭的是伪装，不是加密）。
- **安装向导**默认代理 UDP `8443`（云上比 443 更稳）；仍可改成 `443`。
- **端口跳跃**默认关闭。ISP 只针对单个 UDP 端口限速时，`sudo hy2 hop on` 会让客户端在 `8443-9443` 里随机换端口（Clash 订阅写 `ports` + `hop-interval`，直链端口写作 `8443-9443`）。**云安全组必须放行整段 UDP 范围**（本机 ufw/firewalld 只需放行基准端口），启用后先跑 `sudo hy2 hop check`，再用手机蜂窝网络连续重连 5 次验收；`hy2 hop off` 一键回退。
- **依赖自检**：`sudo hy2 deps` 先认机器（发行版/架构/内存/磁盘余量）再核当前功能所需的命令，`sudo hy2 deps fix` 按 apt/dnf/yum/zypper 只补真正缺的；菜单 26 同效。**不启用的功能不装、不免检**——没开端口跳跃就不碰 iptables/nft，没装 firewalld 就不提 firewall-cmd，小盘机器还会跳过 firewalld/fail2ban 这类几十上百 MB 的大件（可手动装）。
- **面板刷新**：后端每 60 秒采集一次，页面每 10 秒拉一次（切到后台不拉），并标出「数据 N 秒前」。CPU 用两次采集之间的增量算，小机器上不会再恒定显示 0%。
- **面板字体**：自托管 Inter（界面）+ JetBrains Mono（数字/端口/用户名），共约 91KB，走面板同源加载（CSP 下唯一可行）。只含拉丁子集，中文回退到系统字体（苹方/微软雅黑/Noto），不会出现豆腐块。**字体下载失败只是回退系统字体，不影响安装**。不用 Google Fonts / jsdelivr，避免国内不可达。
- **字号**：正文 15px / 行高 1.5（原 13.5px 偏小），表格 14px、表头 12.5px、指标卡数值 24px、辅助文字 13px。指标卡用 `grid-auto-rows:1fr` 保证同行等高；状态列 `white-space:nowrap` + 最小宽度，避免字号放大后「最后 / 客户端」折行把整行撑高一倍。
- **访问站点表**：域名单行显示，超长用 `…` 截断（悬停看全名），点击在**该行下方**展开完整信息（完整域名 / IP / 端口 / 上下行 / 次数 / 占比 / 首末访问时间）。展开行占满整表宽度（`colSpan=10`），不会挤压其他列；同一时刻只展开一行。原先是 `word-break:break-all`，10 列平分 617px 后第一列只剩 23px，「video-edge-abc1234.xyz.cloudfront.net」被折成 13 行、整行高 273px。
- **整机流量**：面板顶部为网卡计数，尽量对齐云厂商套餐；Clash 订阅进度与此同源。
- **用户流量**：用户表为 HY2 代理分摊参考，各用户之和通常小于整机。
- **节点国旗**：订阅与直链的节点名自动带上服务器归属地国旗（如 `🇸🇬 HY2-用户名`）；识别不准时在 `/etc/hy2-aio/config.env` 里加 `COUNTRY_CODE=SG` 这类 ISO 国家码后 `hy2 restart`
- **凭据**：密码/订阅 token 不在 `data.json` 公开；面板内按需复制。
- **禁用/删除即时生效**：Hysteria 的认证只在建立连接时校验，所以改完 `users.json` 还会调 `POST /kick` 把该用户现有连接踢掉（CLI 和面板两条路径都做）。不踢的话，被禁用的人只要不断线就能一直用。
- **备份**：敏感备份仅 CLI，不放在 Web 可下载目录。

## 更新日志

### v2.1.1
- **紧急修复（Caddy 配置校验失败）**：修复 `v2.1.0` 在 `handle /rules/*` 块内嵌套命名匹配器 `@rules_cached` 导致 Caddy 2 报 `unrecognized directive`、`hy2 upgrade` 中断及订阅无法更新的回归问题；改为标准的 `handle /rules/*` 反向代理至后端 `send_ruleset`（自带磁盘缓存直读与按需回源）。

### v2.1.0
- **Clash Fake-IP 与 DNS 修复**：修正 `fake-ip-filter-mode` 误写 `whitelist` 导致 Fake-IP 失效并反噬局域网 `.lan`/`.local` 的问题，改为 `blacklist` 并补齐标准绕过列表；`direct-nameserver` 改用国内纯净 DoH 避免系统 DNS 劫持。
- **Clash 域名嗅探对齐**：新增 `sniffer`（HTTP / TLS / QUIC 纯 IP 嗅探与 `+.push.apple.com` 跳过），与 sing-box 的 `sniff` 行为一致。
- **sing-box 多版本客户端自适应兼容**：同一订阅链接按 `User-Agent`（及可选 `?sbver=` 参数）自动在 `1.14+`（`http_clients` + `store_dns`）、`1.12~1.13`（`download_detour`）与 `1.11`（旧版 DNS 格式）间切换，并开启 `experimental.cache_file` 持久化缓存。
- **Clash / sing-box 同源规则集与单一分流中间层**：Clash 全面切换为与 sing-box `.srs` 1:1 对应的 4 组 MetaCubeX `.mrs` 二进制规则集（`geosite-private` / `geosite-cn` / `geosite-geolocation-!cn` / `geoip-cn`），淘汰裁剪版 `geosite-lite.dat`；`lan` / `local` / `jinritemai.com` 补充规则双端同步。
- **VPS 本机 Caddy `/rules/*` 同源规则缓存分发**：有受信 HTTPS 域名时，订阅内的 `.mrs` / `.srs` 规则地址直接指向 VPS 同源 `/rules/*`（Caddy 静态直出 + 后端多源按需回源缓存 + 离线 302 兜底），彻底避免国内网络拉取 jsDelivr 抽风卡首启；裸 IP 自签证书自动回退公共镜像。
- **协议开关与订阅联动**：面板关闭 HY2 或 VLESS 后，订阅自动隐藏已停用节点并将存活节点设为默认（保留纯手动选择模式，不自动切换）。
- **两端 TUN 与 DNS 边界对齐**：两端统一 `stack: mixed` 并排除 `PUBLIC_IP/32` 防环路，Clash 补齐 `100.64.0.0/10`、`169.254.0.0/16`、`224.0.0.0/4` 私网段，sing-box 1.12+ 补齐 `HTTPS/SVCB` DNS 查询拦截。
- **双内核双向分流验收**：`tools/verify-domestic-routing.py` 支持同时拉起真 `mihomo` 与真 `sing-box` 校验“国内必直连 + 海外必代理”，Linux 全量 713 项单测通过。

### v2.0.1
- **面板体验修复**：修复 `#vlessOffBanner` 误写 `class="banner banner-muted"` 导致 VLESS 运行时仍在顶部裸露显示的问题，对齐 `class="notice"` 样式与显隐逻辑。
- **检查更新先比对哈希**：新增 `POST /upgrade/check`，前端点击「检查更新」先对比本地版本与远端最新 Release 的提交哈希；一致时直接提示「已是最新版本，无需更新」，发现新版本再弹窗展示版本/哈希对比并由用户确认后触发更新重启。

### v2.0.0
- **模块化架构重构**：前端独立拆出 `web/index.html`，后端拆分为 `app/server.py`、`app/common.py`、`app/subscription.py`、`app/activity.py`、`app/backup_ops.py`、`app/rebuild_config.py`、`app/rebuild_xray.py`，Shell 拆出 `lib/network.sh` 并统一 `dispatch_cli_command`，全部 22 个模块纳入 `SHA256SUMS` 校验。
- **安全修复（防 Cloudflare ProxyIP 盗刷）**：默认 Reality 回落站改为 `www.apple.com:443`，老版本升级时自动将旧 `www.cloudflare.com:443` 迁移至 `www.apple.com:443` 并保留原有密钥与端口。
- **面板新功能**：服务卡片新增「关闭 VLESS / 开启 VLESS」独立开关（重启持久化）；功能抽屉新增「维护」区块，支持「检查更新（异步升级并自动刷新）」与「重启内核」。
- **兼容性验证**：新增 `v1.8.7` 旧结构升级到模块化架构的端到端自动化演练，全量 706 条单测在 Linux 通过。

### v1.8.7

全仓自检与稳定性修复汇总（重构前的稳定基线版本）：

- **升级与版本检测**：修复 `AIO_VERSION` 带 commit 后缀导致 release 轨道 `hy2 upgrade` 无法跳过、以及交互菜单永久误报「可升级」的问题。
- **端口修改（CLI 与面板）**：
  - 修复 `hy2 port hy2 <范围>` 新起点被拒、同起点跳过、从端口跳跃切回单端口时残留 `PORT_HOP_ENABLED=true` 导致配置撕裂的问题；
  - 补齐范围与 VLESS 端口冲突校验、重建失败显式报错与本机 ufw/firewalld 放行同步；
  - 面板改端口（`POST /ports`）改为通过 `/run/hy2-aio/port-result` 回传 root 侧真实错误，不再静默吞错报「成功」。
- **面板静态资源与依赖自检**：
  - 安装与 `repair` 时同步复制 `assets/` 到 `modules/`，资源回退下载兼容 `REPO_URL`（二维码库无环境变量时仍可走 jsdelivr 镜像）；
  - 修复 `hy2 deps fix` 补装成功后仍误报「缺少基础依赖」并返回 1 的 Bug，以及 `hy2 deps` 只读体检越权安装二维码库的问题。
- **后端、CLI 与前端细节**：
  - 面板禁用/删除/轮换用户改为在 Hysteria 重载新配置完成后再踢下线，避免窗口期重连绕过；
  - `hy2 restart` 检测到 `XRAY_PORT` 变更时直接重建并等待后端就绪后再同步；
  - 补齐 `bash hy2.sh cert` 命令分发；
  - 修复日志站点重复计次与客户端 IP 最近活跃时间漂移；
  - sing-box VLESS 节点 tag 补齐国旗前缀；
  - 面板补齐 `localStorage` 异常兜底与 `Escape` 关闭二维码/端口弹窗；
  - 隔离 `test_caddy_install.py` 对宿主机 `/usr/bin/caddy` 的依赖（Linux 全量 692 例单测通过）。

### v1.8.6

修复 **YouTube 完全打不开** —— 根因是 DNS 被污染，且旧配置把境外域名交给了系统 DNS。

#### 现象

用脚本装好之后，YouTube 视频始终加载不出来（"完全没法看"，不是慢）。

#### 根因：DNS 污染 + `dns.final = local`

真机实测（`nslookup rr5---sn-a5msenes.googlevideo.com`）：

```
2a03:2880:f11f:83:face:b00c:0:25de    ← face:b00c 是 Facebook 的标志性 IPv6 段
108.160.172.1                          ← Dropbox 的段
```

客户端日志里 `googlevideo.com` 也被解成一串**根本不属于 Google** 的 IP：

```
31.13.94.37 / 31.13.95.169 → Facebook 段
199.59.149.230             → Twitter
59.24.3.173 / 74.86.151.167
```

而旧配置的致命点是：

```json
"dns": { ..., "final": "local" }
```

`final: local` 意味着**所有没命中规则的域名都走系统 DNS** —— 也就是被污染的那个。
所以即使路由规则正确（v1.8.5 已修），代理也是去连这些假 IP：
拿 `SNI=googlevideo.com` 去连 `Facebook:443`，握手必然失败。

Clash 那份同理：`nameserver` 全用国内 DoH（doh.pub / alidns），
递归查询境外域名时同样返回污染结果。

#### 修法：境外域名经代理走 DoH

sing-box：

```json
"servers": [
    {"type": "https", "tag": "remote", "server": "1.1.1.1", "detour": "proxy"},
    {"type": "https", "tag": "remote-alt", "server": "8.8.8.8", "detour": "proxy"},
    {"type": "local", "tag": "local"}
],
"rules": [
    {"domain_suffix": [".cn"], "server": "local"},
    {"rule_set": "geosite-cn", "server": "local"}
],
"final": "remote"
```

`detour: proxy` 让 DoH 查询本身**经代理发出**，绕开本地污染。
国内域名仍走 `local`（快，且国内域名不会被污染）。

Clash：

```yaml
nameserver:
  - https://1.1.1.1/dns-query#PROXY
  - https://8.8.8.8/dns-query#PROXY
nameserver-policy:
  "geosite:cn":
    - https://doh.pub/dns-query
    - https://dns.alidns.com/dns-query
```

`#PROXY` 后缀让 mihomo 经代理去查。

#### 为什么之前"看着正常"

国内站点不受影响（域名走 local，IP 也是国内的）；
只有**境外域名**才会踩到污染 —— 所以表现就是"能上国内网，YouTube 死活打不开"。

#### 自动化验收

新增 5 项 `DnsPollutionGuardTests`：

| 用例 | 校验点 |
|---|---|
| `test_singbox_dns_final_is_not_local` | `dns.final` 不能是 local |
| `test_singbox_remote_dns_uses_proxy_detour` | 境外 DoH 必须 detour 到 proxy |
| `test_singbox_domestic_domains_use_local_dns` | 国内域名仍走 local |
| `test_clash_foreign_dns_goes_through_proxy` | Clash 境外 nameserver 带 `#PROXY` |
| `test_clash_domestic_policy_still_local` | Clash 国内策略仍走国内 DoH |

负向三组各自精确变红：final 改回 local → 1 红；去掉 detour → 1 红；Clash 去掉 `#PROXY` → 1 红。
另用真 sing-box 1.14.4 `check` 验证配置合法（含 `dns.rules` 跨引用 `rule_set`）。

#### 客户端要做的事

**更新订阅**（DNS 配置在订阅里）。服务端先 `sudo hy2 upgrade && sudo hy2 restart`。

### v1.8.5

修复分流规则顺序 —— **YouTube / Google 视频起播 5 秒超时**。

#### 现象

真机日志里唯一一条 ERROR：

```
ERROR ... open connection to 118.193.240.37:443 using outbound/direct[direct]:
      dial tcp 118.193.240.37:443: i/o timeout
```

追上去发现该 IP 是 `rr5.sn-qja5mc-5q.googlevideo.com` 的解析结果
—— YouTube CDN 在国内的缓存节点（联通陕西）。

#### 根因

规则曾经写成一条：

```json
{"rule_set": ["geosite-cn", "geoip-cn"], "outbound": "direct"}
```

`rule_set` 数组是 **OR** 关系：`geoip-cn` 一命中就直接直连，
**域名判断被完全绕过**。

于是「海外域名 + 国内 CDN IP」这类组合全被判成直连：
`googlevideo.com` 在境内有 CDN 缓存，解析出来的就是国内 IP，
但它们经常不可用/被干扰 → 5 秒超时 → 视频起播失败。

Clash 那份 `GEOSITE,cn,DIRECT` + `RULE-SET,china-ip,DIRECT` 是同一个坑。

#### 修法：域名优先、IP 兜底

拆成三条，顺序不能变：

```json
{"rule_set": ["geosite-cn"], "outbound": "direct"},              // 国内域名 → 直连
{"rule_set": ["geosite-geolocation-!cn"], "outbound": "proxy"},  // 海外域名 → 代理
{"rule_set": ["geoip-cn"], "outbound": "direct"},                // 纯 IP 兜底 → 直连
```

新增 `geosite-geolocation-!cn` 规则集（166KB，jsdelivr 镜像）。
Clash 对应加 `GEOSITE,geolocation-!cn,PROXY`，同样挡在 `china-ip` 之前。

**注意 `rule_set` 是 OR 不是 AND** —— 把国内和海外两套规则塞进同一条，
IP 一侧会抢跑，域名一侧永远不生效。这是本次的教训。

#### 保留的行为

- 微信图片/视频（纯 IP 直连）仍由 `geoip-cn` 兜底，不受影响
- 国内域名仍走直连
- 只有「海外域名解析到国内 IP」这一种情况从直连改成了代理

#### 自动化验收

新增 4 项 `DomainBeforeIpRuleOrderTests`：

| 用例 | 校验点 |
|---|---|
| `test_singbox_rules_are_not_merged` | 禁止合并成 OR 单条 |
| `test_singbox_overseas_domain_rule_before_geoip` | 海外域名规则必须在 geoip 之前 |
| `test_singbox_has_overseas_ruleset` | 规则集定义存在 |
| `test_clash_overseas_domain_before_china_ip` | Clash 侧顺序同样正确 |

负向三组各自精确变红：合并回 OR → 2 红；调整顺序 → 1 红；删 Clash 规则 → 1 红。
另外用真 sing-box 1.14.4 `check` 验证生成的配置合法。

#### 客户端要做的事

**更新订阅即可**（服务端配置变了，客户端拉新配置）。
服务端执行 `sudo hy2 upgrade && sudo hy2 restart`。

### v1.8.4

紧急修复。**面板里的二维码一直不显示**（扫码导入订阅失败）。

#### 根因

`hy2.sh` 的下载清单 `local assets=(...)` 里只有字体和客户端图标，
**漏了 `assets/vendor/qrcode.min.js`**。

于是链条断在第一步：

1. 安装时该文件从未被下载到 `/usr/local/lib/hy2-aio/modules/assets/vendor/`
2. `install_panel_vendor` 先查这个本地副本 → 查不到
3. 只能去拉 `raw.githubusercontent.com` → 国内直连必超时
4. 二维码静默缺失，面板扫码区域空白

> 这和 v1.8.3 修的 `bad substitution` 是同一次改动（新装机三连坑）留下的两个洞：
> 自检写好了，但没人把文件真正下载下来。

#### 修法

- `assets` 清单补上 `assets/vendor/qrcode.min.js`
- `mkdir` 补上 `assets/vendor` 目录
- 校验段对 `*.js` 加正文检查（`head -c 200 | grep -q qrcode`）——
  js 没有 magic number，不加这层的话 CDN 返回的 404/错误页会被当成正常文件落盘

#### 已经卡住的机器怎么办（不用等发版，立即生效）

```bash
sudo mkdir -p /var/www/hy2-aio/vendor
sudo curl -fsSL "https://testingcf.jsdelivr.net/gh/keiraee/hy2-allin-one@main/assets/vendor/qrcode.min.js" -o /tmp/qrcode.min.js
sudo sh -c 'echo "4ee9e4db9666ed5c38c508c0cb57512465fcbc5a653ebf9fa33c0c37c71b15bf  /tmp/qrcode.min.js" | sha256sum -c'
sudo install -m 0640 -o hy2-aio -g caddy /tmp/qrcode.min.js /var/www/hy2-aio/vendor/qrcode.min.js
sudo rm -f /tmp/qrcode.min.js
```

然后 **Ctrl+F5 强刷面板**（或用无痕窗口），二维码即出现。

#### 自动化验收

新增 3 项回归：

- `test_download_list_contains_qrcode` —— 清单必须含该文件
- `test_vendor_dir_created` —— 必须创建 `assets/vendor` 目录
- `test_js_body_is_validated` —— js 必须有正文内容校验

负向三组各自精确变红：删清单项 → 1 红；删 mkdir → 1 红；删正文校验 → 1 红。

#### 新机器 / 已装机器

- 新装：直接用 v1.8.4 的安装命令
- 已装：`sudo hy2 upgrade && sudo hy2 restart`

### v1.8.3

紧急修复。**新装机/`hy2 repair` 会在依赖自检阶段直接中断，装不下去。**

#### 根因

`lib/deps.sh` 里二维码库检查写成了：

```bash
[ "${#PANEL_VENDOR_FILES[@]:-0}" -eq 0 ]
```

`${#arr[@]}` 是数组长度，**后面不能接 `:-` 默认值**（那是给普通变量用的）。
bash 判定为语法错误，直接抛 `bad substitution`；再叠上 `set -Eeuo pipefail`，
整个安装就在这一行中断：

```
HY2 AIO 运行环境自检
系统：Debian GNU/Linux 13 (trixie)  架构：x86_64 (amd64)
内存：943MB  根分区：26GB（可用 24424MB）  包管理器：apt

[09:01:51] 无需补装
/tmp/.../lib/deps.sh: line 259: ${#PANEL_VENDOR_FILES[@]:-0}: bad substitution
```

讽刺的是这行本来是「panel.sh 没加载就早退跳过」的保护分支，结果自己先炸了。

#### 修法

先判存在性再取长度，两条路都安全：

```bash
local panel_vendor_count=0
if [ -n "${PANEL_VENDOR_FILES+set}" ]; then
  panel_vendor_count=${#PANEL_VENDOR_FILES[@]}
fi
if [ "${PANEL_VENDOR_DIR:-}" = "" ] || [ "$panel_vendor_count" -eq 0 ]; then
```

注意**不能**简单退化成裸 `${#PANEL_VENDOR_FILES[@]}` —— `set -u` 下未定义数组会报 `unbound variable`，同样中断安装。

#### 自动化验收

- `test_check_survives_undefined_panel_vendor_array`：目录有值、文件数组未定义时不崩
- `test_qr_check_still_active_when_panel_loaded`：反向守护，变量齐备时二维码缺失仍要报警（防止修成死代码）
- 负向三组各自精确变红：改回 `:-0` → 2 红；改裸写法 → 1 红（unbound variable）；改成永远跳过 → 1 红

#### 影响范围

v1.8.2 的所有**新装机和 repair**。已装好且能正常运行的机器不受影响（这行只在依赖自检时执行）。
装 v1.8.2 失败的机器，用 v1.8.3 重新执行安装命令即可，无需清理。

### v1.8.2

紧急修复。**sing-box 用户:连没有 IPv6 的 Wi-Fi 时,国内 App(抖音搜索、小红书头像、微信大图)全部转圈**。

#### 根因

订阅里的 sing-box 配置**没有关掉 IPv6 解析**(Clash 那份有 `ipv6: false`,sing-box 这份漏了)。
Wi-Fi 无 IPv6 时,sing-box 先把国内域名解析成 AAAA(如 `2408:...` 联通 v6 段),
判为「国内 → 直连」,再让 `direct` 经 wlan0 去连 v6 地址:

```
inbound connection to [2408:876c:1740:150::8e]:443
outbound/direct[direct]: outbound connection to [2408:876c:1740:150::8e]:443
ERROR: dial wlan0 (24): dial tcp [2408:...]:443: connect: network is unreachable
```

请求全部失败、App 超时重试 → 表现为「加载不出来 / 头像转圈」。

这解释了三个现象:**切 VLESS 没用**(走的是 direct 直连那条路,与出站协议无关)、
**只有 Wi-Fi 出问题、蜂窝正常**(蜂窝有 v6 所以直连通)、**Clash 正常**(有 `ipv6: false`)。

#### 修法

- sing-box 的 `dns` 加 `"strategy": "ipv4_only"`(等价 Clash 的 `ipv6: false`)
- tun `address` 去掉 IPv6 段,只留 `172.19.0.1/30`
- tun 顺手显式收窄 `mtu: 1400`(默认偏大,撞 PPPoE 1492 之类小 MTU 链路会分片丢包)

#### 自动化验收

- `test_dns_strategy_is_ipv4_only` / `test_tun_has_no_ipv6_address` / `test_tun_mtu_is_narrowed`
- 关键域名清单补抖音 CDN(`api.amemv.com` / `aweme.snssdk.com` / `douyinpic` / `douyinvod`)
  与小红书(`www.xiaohongshu.com` / `sns-webpic-qc.xhscdn.com`)

#### 客户端要做的事

**只需「更新订阅」**(订阅 URL/token 未变)。

### v1.8.1

紧急修复。**微信图片/视频加载不出来**（两人手机都中招，关掉代理重连才恢复）。

#### 根因

v1.8.0 为了避开 6.5MB 的 `geoip.dat`（国内网络拉不动会卡首启），把 `GEOIP,CN` 删了，只留 `GEOSITE,cn`。但 **GEOSITE 只匹配域名** —— 微信图片/视频 CDN 大量**直接用 IP 连接**（不走域名解析），这些连接匹配不到任何规则，落到 `MATCH,PROXY` → 全部绕道日本/美国 → 加载转圈。

真机日志对照（同一台手机、同一个 IP）：

```
36.155.189.213:80
  v1.8.0 订阅 → match Match using PROXY[🇯🇵]         ← 转圈
  v1.8.1 订阅 → match RuleSet(china-ip) using DIRECT ← 秒开
```

#### 修法

补回 IP 段规则，但用 **mrs 格式（37KB，0.3 秒下完）** 而不是 `geoip.dat`（6.5MB）：

```yaml
rule-providers:
  china-ip:
    behavior: ipcidr
    format: mrs
    url: .../MetaCubeX/meta-rules-dat@meta/geo/geoip/cn.mrs
rules:
  - GEOSITE,cn,DIRECT
  - RULE-SET,china-ip,DIRECT   # 新增：纯 IP 连接也直连
  - MATCH,PROXY
```

#### 新增验证工具

- `tools/verify-ip-coverage.py`：起真 mihomo 逐个验证国内 IP 是否直连，非 `DIRECT` 即 FAIL
- 清单在 `tests/test_domestic_coverage.py`（`CRITICAL_DOMESTIC_DOMAINS` 域名 + `CRITICAL_DOMESTIC_IPS` IP）
- 实测小k 抓的 7 个微信真实 IP：全部 `RuleSet(china-ip) using DIRECT` ✓

#### 客户端要做的事

**只需「更新订阅」，不用重新导入**（订阅 URL 和 token 未变，服务端返回 `cache-control: no-store`）。

### v1.8.0

国内流量不再靠手写域名清单，改用 geosite 内置数据 + 自动化验收。

#### 国内分流

- **Clash 改用 `GEOSITE,cn`**（11 万条，MetaCubeX 维护、持续更新），替代原 blackmatrix7 远程规则集。上游清单实测漏 `jinritemai.com`（抖店商家端），导致抖店被 `MATCH` 兜底抓到日本代理、明显变慢。现在 geosite 为主力，只对缺口补手写规则（当前仅 1 条：`jinritemai.com`）
- **geosite 用 lite 版**（`geosite-lite.dat`，176KB，CN 分类记录数与全量 4.3MB 版一致）。全量 `geoip.dat` 6.5MB，国内网络 30 秒只能拉 620KB，mihomo 会卡在 `Can't find GeoIP.dat` 起不来 —— 已移除 `GEOIP,CN`，只依赖 geosite
- **geox-url 走 jsdelivr 镜像**：`raw.githubusercontent.com` 在国内拉不动
- **Clash DNS 改国内优先**：`nameserver` 用 doh.pub / alidns，`nameserver-policy` 里 `geosite:cn` 走国内 DoH，`direct-nameserver: system`。原配置只有 1.1.1.1/8.8.8.8（全境外），fake-ip 模式下国内 CDN 被解析到境外节点，即使规则直连也在绕远
- **sing-box 补国内分流**：新增 `geosite-cn` + `geoip-cn` rule-set（jsdelivr 镜像），rules 顺序 `sniff → hijack-dns → 私有网段直连 → 国内直连 → 其余走代理`。修复 iOS sing-box 导入后微信发不出图片（图片走国内 CDN 通道被 tun 全量代理，文本走长连接所以正常 —— sing-box issue #2492 的已知问题）
- **sing-box 的 Hysteria TLS 不再硬编码 `insecure: true`**：SNI 改用订阅证书域名（`DOMAIN`），`insecure` 按 `CLIENT_INSECURE` 判定。v2rayNG 26.2.6+ 会拒绝「未加密连接」的节点，原配置升级后必弹窗
- **新增自动化验收工具** `tools/verify-domestic-routing.py`：起真 mihomo，逐个访问 22 个关键国内域名（抖店/微信/百度/淘宝/B站/知乎/京东/12306/QQ/阿里/腾讯/头条/西瓜/飞书…），解析命中规则，非 `DIRECT` 即 FAIL。清单在 `tests/test_domestic_coverage.py`，新增域名加一行即可
- **订阅里不再写解释性注释**：给用户的 YAML 是纯配置
- **版本号随提交自动变化**：`1.8.0.<提交数>.g<短哈希>`，`upgrade` 写入 config.env，面板不再永远显示同一个号
- **`hy2.sh` 默认 tag 从 v1.7.3 → v1.8.0**（v1.7.3 / v1.7.4 都不含本次分流修复，新机器装旧版会直接踩坑）

#### 端口跳跃（默认关闭）

- 新增 `hy2 hop on|off|show|check`：服务端用 Hysteria 内置 `listen` 范围 + 自动 nft/iptables 重定向，订阅写 `ports` / `hop-interval`，直链写 `mport`。范围必须从 `HY2_PORT` 开始、跨度 ≤2000
- `hy2 hop check` 7 项自检：防火墙工具、`CAP_NET_ADMIN`、进程监听、重定向规则、本机防火墙基准端口、残留 NAT 链，并提示云安全组需放行的 UDP 范围
- 修复：端口跳跃开着时快速重启（间隔 <1 秒）会留下未清理的 NAT 链，下次 `iptables -N` 撞名 FATAL（`Chain already exists`），服务起不来、面板报 `traffic API Connection refused`。现在 `hy2 restart` 先停服务 → 清 `HYSTERIA-PR-*` / `hysteria_*` 残留 → 再启动（只按这两个前缀精确匹配，不动其他规则、不碰 users.json / state.json）
- 修复：`hop on` / `hop range` 的自动回滚形同虚设 —— `apply_hysteria_client_settings` 里 restart 失败返回非零，`set -Eeuo pipefail` 就地退出，回滚判断永远执行不到。现把调用兜住并纳入回滚条件，`hop off` 同类问题一并修
- 修复：范围只有两个端口时（如 `8443-8444`）自检 5/6 必定误报「没找到重定向规则」 —— Hysteria 在 `start == end` 时只写单端口
- 修复：代理端口 65535 时 `hop on` 抛「结束端口必须大于开始端口」，改为明确提示先改小端口
- 修复：只装 iptables 没装 ip6tables 的机器，开端口跳跃后 Hysteria 直接拒绝启动（监听通配地址要求两个都在）

#### 依赖自检与小机器

- 新增 `hy2 deps` / `hy2 deps fix`（菜单 26）：先识别发行版、架构、内存与磁盘余量，再检查**当前功能真正需要**的命令；`fix` 按 apt/dnf/yum/zypper 只补缺项，未启用功能一律不碰，小盘机跳过 firewalld/fail2ban 这类大包。安装流程装完基础包后自动核一次，<600MB 提示启用 swap，根分区 <3GB、架构不在 amd64/arm64 时告警
- 精简基础安装清单：去掉从未被调用的 `jq`（全仓 JSON 都用 `python3 -c`），也不再预装 ufw/firewalld/fail2ban/nftables/iptables —— 小机器磁盘紧

#### 面板

- 修复：面板永久卡在「正在读取数据」 —— 逐行编辑改版时删了 HTML 元素但 JS 绑定区残留一行 `$("portCancel").onclick=...`，在 null 上赋值抛 TypeError，整个 `<script>` 中断，末尾的 `load()` 永远不执行。现删除死绑定，并新增静态扫描测试（所有 `$("id")` 必须存在于 HTML）
- 修复：`load()` 失败后永久卡死 —— 加指数退避自动重试（2s/4s/8s/16s/30s，最多 5 次，成功归零）
- 端口设置改为**逐行独立编辑**：每行（HY2 / VLESS）有自己的「编辑 / 取消 / 应用」按钮，打开弹窗两行都锁定，改哪行点哪行。应用时只有该行提交，成功 1.5 秒后回锁定态
- 修复：面板 CPU 长期显示 0% —— 旧实现固定 120ms 采样窗口，100Hz 内核单核只有 12 jiffies，1% 负载折算 0.12 jiffies，四舍五入永远 0.0%。现改为「两次采集之间的增量」（60s 窗口 = 6000 jiffies/核，分辨率提高约 500 倍），采集间隔 <1 秒沿用上次读数
- 面板刷新从 60 秒改为 10 秒（切后台不拉），更新时间后标「数据 N 秒前」；CPU 负载旁补核数
- 字号整体上调：正文 13.5px → 15px、表格 13 → 14px、指标卡数值 20 → 24px。同时修掉指标卡等高问题、状态列折行问题
- 字体自托管：Inter + JetBrains Mono（4 个 woff2 共 91KB，同源分发），各平台一致；缺失只 warn 不中断
- 修复：访问站点表长域名被挤成竖排单字（`.dest-host` 用 `word-break:break-all` 导致 23px 列宽折 13 行），改为单行 + `ellipsis` + `max-width:240px`，点击在行下方展开详情
- 修复：归属地查询失败被永久缓存，一次网络抖动就让国旗一直不出现（只能重启后端），现失败只记 1 小时
- 修复：国旗只加在面板和订阅上，`hy2 show` 与 `/root/hy2-aio-access.txt` 里节点名还是旧的，现由后端落进 `data.json` 供 CLI 复用
- 面板新增「端口」按钮：可在面板直接改 HY2 / VLESS 端口（走 cmd 文件 + path unit 以 root 执行）

#### 内核与统计

- 默认内核升到 Hysteria **2.14.0**（原 2.12.1）：2.12.3 修了端口跳跃规则误重定向出站 UDP 的 bug，2.14.0 带 UDP 转发性能提升（小包约 +30%）。已用真二进制验证完整配置可正常加载。想钉旧版可 `HYSTERIA_VERSION=v2.12.1`
- `hy2 status` 显示内核版本，低于内置默认时提示 `hy2 update`（只提示不自动升级）
- 新增 `POST /kick`：禁用 / 删除 / 轮换密钥时把该用户现有连接踢掉。Hysteria 的 userpass 只在建连时校验，原先只改 `users.json` 的话被禁用的人不断线就能一直用（**真实漏洞**）。CLI 与面板两条路径都覆盖，踢人失败不影响主操作
- 修复：Hysteria 重启后用户流量少算 —— per-user 计数器从 0 重来，而 `counter_delta` 拿新值跟旧基线比（实测能少算 80%+）。现在用 `/proc/<pid>/stat` 的 `starttime` + PID 判断进程是否换过，换了就清零基线；拿不到标识时安全退化

#### 证书与安全

- Hysteria 复用 Caddy 的 Let's Encrypt 证书（原来用 openssl 自签，`CN=IP` 且 SAN 只有 IP，严格校验的客户端直接失败）；`hy2 repair` 会刷新证书
- 修复 VIOLESS 端口被运营商 DPI 干扰：新增 `hy2 port` 命令（`show` / `hy2 <端口|范围>` / `vless <端口>`），改端口后自动重建配置并重启内核

### v1.7.3
- 修复 v1.7.2 卸载重装后 Hysteria 起不来（`Failed at step CHDIR`）：官方安装脚本的服务单元用 `WorkingDirectory=~`（hysteria 用户家目录），v1.7.2 把用户创建提前后家目录变成 `/nonexistent`；现统一为 `/var/lib/hysteria`，安装与 repair 自动改回坏家目录并补目录，已中招机器升级即修复、无需重装
- 订阅与直链的节点名自动带上服务器归属地国旗（如 `🇸🇬 HY2-用户名`）；按 IP 归属地自动识别，识别不准可在 config.env 设 `COUNTRY_CODE=SG` 这类 ISO 国家码覆盖
- 修复安装半途失败后重跑 `install` 报「已安装」的死胡同：config.env 在但缺 `hy2` 命令时自动续装修复并拉起服务；`hy2` 命令行入口改为服务启动前安装，服务起不来时 `hy2 repair` / `hy2 restart` 仍可用
- 新增菜单/命令「重新申请证书」：安装完成但面板/订阅 HTTPS 证书没签下来（云机安全组未放行 TCP 80、ACME 验证超时很常见），进菜单选 25 或 `sudo hy2 cert` 重试——清掉该域名失败签发状态、重启 Caddy 触发重新申请，轮询约 1 分钟检查结果，成功打印签发者与有效期，仍失败给出常见原因

### v1.7.2
- 卸载重做为**完全卸载**：逐个停止服务 → 卸载 Hysteria / Xray / Caddy（含软件源）→ 清配置、数据、用户、防火墙（含 80/tcp），结尾校验无残留，卸载后可直接重装
- `HY2_PURGE` 两段式废弃，`hy2 uninstall` 默认即完全删除；要留数据请先 `hy2 backup`

### v1.7.1
- Caddy 软件源挂掉（如 Cloudsmith 402）不再中断安装：禁用坏源后改试系统仓库，最终兜底官方二进制（SHA256 校验）
- config.env 提前落盘；安装任意一步失败后可直接 `bash hy2.sh repair` 续装，repair 自动补齐缺失的 Hysteria/Xray/Caddy

### v1.7.0
- 安装向导套餐流量支持 MB/GB/TB/无限流量，先选单位再填数值；无限套餐显示「无限 · 不限量」
- 订阅导入名不再带引号反斜杠和 `.yaml` 后缀（Clash Verge Rev），订阅头上行/下行与面板方向对齐
- 面板 API 只收 application/json、拒绝 `Origin: null`，同源校验补上默认端口比较（CSRF 纵深防御）
- 面板密码不再进进程参数，hash-password 改走 stdin；修复升级时 caddy 报 "Error: EOF"
- CLI 删用户后保住 state.json 归属权限并清掉站点/IP/流字节残留，不再连带清零全员流量统计
- state.json 损坏先留副本并在面板报错，不再静默清零统计；删用户的统计残留不再被采集「复活」
- hy2-xray 启动前回收被残留官方 Xray 占用的端口，不再端口冲突无限重启
- `hy2 on` / 面板开启改用 restart，已运行时新配置立即生效
- `hy2 rollback` 非交互不再静默取消（脚本用 `HY2_YES=1`）；disabled 字段为字符串时状态不再分裂
- 升级遇 GitHub 429/瞬断自动重试；main 轨道提交未变时跳过，不再白打快照重启

### v1.6.1
- 修复：Hysteria 统计用户名与面板大小写不一致时，用户流量一直显示 0

### v1.6.0
- 加入官方 Xray-core **VLESS+Reality+Vision** 作为 TCP 兜底；新装与升级都会自动拉对应 CPU 架构的内核
- Clash 订阅里两个节点手动选：主节点仍是 `HY2-用户名`，备用固定叫 **hy2超时备用临时节点**（不是自动 fallback）
- 复制直链一次两行：`hysteria2://` 和 `vless://`；Reality 伪装站默认 `www.apple.com:443`
- 默认与 HY2 同端口号：HY2 走 UDP，VLESS 走 TCP；面板仍占 443。`hy2 off` 只关 Hysteria，VLESS 继续可用
- 单独升内核：`hy2 update` 升 Hysteria，`hy2 update-xray`（或 `hy2 update xray`）升 Xray
- 修复：`hy2 restart` / 安装 / 回滚时 Xray 因 `/run/hy2-aio` 被清而 `226/NAMESPACE`
- 改模块后补齐 `SHA256SUMS`，避免 `hy2 upgrade` 校验失败
- `hy2 upgrade` 同版本仍比对提交哈希；正式版 tag 原地更新也会继续拉模块
- 添删用户先落盘回成功，再后台重启内核，避免走代理打开面板时误报「用户已存在 / 不存在」

### v1.5.0
- 面板改成极简仪表盘风格，指标、服务、用户表回到同一页
- 内联 SVG 线框图标（不加载外链）；修好精灵根标签写错导致图标全空白
- 流量分析弹窗铺满、数字列右对齐、窄屏分表藏列、菜单超出视口可滚动
- `main` 升级按 commit SHA 拉模块，避免 GitHub raw 把 SHA256SUMS 缓存住；日志打印上次/本次哈希
- 添加用户立刻回面板，重复添加不再误报「用户已存在」；改备注不再重启 Hysteria
- 写入时全屏蒙层和按钮转圈，避免连点
- 升级写成一行：`hy2 upgrade && hy2 restart`

### v1.4.0
- 用户行菜单新增流量分析：接近全屏双栏看板，热力、作息、趋势、按日、上下行、站点构成一次看完
- 从 Hysteria 日志解析客户端 IP、访问站点、首次/最近访问时间和连接时长；表格可排序
- 用户表增加速率模式、历史累计；整机进度条按用量变色；侧边栏可手动备份
- 记住 `HY2_REPO_REF=main` 升级轨道，正式安装默认仍跟 Release，不会被 main 带跑
- 修复：空图表占位、窄屏合计列被藏、顶栏 `vundefined`、菜单升级提示空值等

### v1.3.28
- 修复：已是最新版时敲 `hy2` 只印 banner 就退出（升级提示空值触发 `set -e`）

### v1.3.27
- 敲 `hy2` 进菜单时探测 GitHub latest Release，有更新提示可升级
- 面板可导出 Hysteria / 面板 / Caddy 日志（默认最近 24 小时，与菜单 18 同源）

### v1.3.26
- 安装/升级结束显示 Welcome HY2 作者横幅与开源地址
- 首次安装直接打印面板账号和密码，不再只提示去看 txt
- 新增 `hy2 panel` / 菜单 23 查看面板账号和密码

### v1.3.25
- Clash 订阅默认规则分流：国内域名/IP 直连，其余走 HY2（blackmatrix7 China + MetaCubeX CN IP）
- `hy2 upgrade` 本机版本已是 latest 时跳过，不再重复拉取模块
- 兼容旧 Clash 订阅 URL（无 `/s/` 前缀）

### v1.3.24
- 面板与 CLI 增加 Hysteria 开/关（`hy2 on` / `hy2 off`）；全员禁用自动关服，不再写隐藏占位账号
- 关闭时面板显示「已关闭」，不再因统计口 Connection refused 刷红条
- `hy2 restart` 先等统计口就绪再拉后端，避免升级后短暂读不到流量
- `hy2 upgrade` 绕过 GitHub raw CDN 缓存，避免刚推完仍拉到旧模块

### v1.3.23
- 升级日志改为「当前版本 → 目标版本」，不再写「升级 HY2 AIO → vX」
- 自动备份只打包必需文件，目录里读不了的残留不再导致整次失败
- tar 报错显示真正原因；失败后一小时再试，不再每分钟刷面板
- 面板错误条可关闭；同一条关掉后不会反复跳出

### v1.3.22
- 修复：upgrade 写 Caddy 配置时触发 `BACKEND_HOST: readonly variable`，repair 中途退出
- restart 前执行 `systemctl daemon-reload`，避免 unit 已改未加载的告警

### v1.3.21
- 备份失败不再报成功；校验归档必含私钥等关键文件，去掉重复打包
- fail2ban 按 Caddy JSON 访问日志匹配面板 401
- 非 Debian 安装尊重系统包提供的 Caddy 路径与 unit
- 管理面板强制 HTTPS，拒绝端口 80
- 回滚快照补齐 Caddy 片段、reload unit 与 hy2 CLI；归档改到 root-only 目录并校验成员
- 面板与 CLI 用户修改改为跨进程锁 + 失败回滚
- 安装前检查面板/统计/后端端口冲突与真实占用
- Caddy 旧站点检测改为域名字面量匹配，避免误覆盖近似站点
- 卸载会清掉站点片段、reload unit、fail2ban 与 sysctl；`HY2_PURGE=1` 可删数据
- `hy2 upgrade` 始终按 `HY2_REPO` / ref 拉远程模块，不再误用仓库旁边的旧 `lib/`
- 用户流量改为增量统计，避免 Hysteria `clear=1` 后崩溃丢数；删用户同步清理模式与历史状态

### v1.3.20
- 全面修正面板可写权限：/etc/hy2-aio=0770，/etc/hysteria=2770，config.yaml=0660
- 避免安装/CLI 操作后又把目录改回 0750/0640 导致面板用户操作失败

### v1.3.19
- 面板后端启动时自检可写目录；权限/超时错误直接返回原文，不再只显示「内部错误」
- repair 强制纠正 /etc/hy2-aio 与 Hysteria 配置目录权限

### v1.3.18
- 修复：面板添加用户 Permission denied（/etc/hy2-aio 误用 0750，后端无法写 users.json.tmp）

### v1.3.17
- 修复：安装向导提示文字被写进 HY2_PORT/OBFS_ENABLED，导致 config.env 非法行

### v1.3.16
- 重构交互菜单：维护/账号/功能分组；补 repair、回滚、用户列表
- 菜单缺命令时提示先 hy2 upgrade，避免旧版 command not found

### v1.3.15
- 修复：菜单「1) 安装」报 install_stack: command not found；已装机器引导用 upgrade

### v1.3.14
- 修复：hy2-aio 重写 config.yaml 后 Hysteria 无法读取（permission denied）
- restart 前自动纠正 /etc/hysteria 权限

### v1.3.13
- CLI 安装到 /usr/local/bin（普通用户也能找到命令）；帮助不再写死 sudo
- 支持 hy2 -help；提示改为「需 root」

### v1.3.12
- 修复：已安装环境下 `bash hy2.sh repair` 误从家目录拷贝 lib（cp: cannot stat）
- 新增：`sudo hy2 upgrade` 自动拉 GitHub 最新版（之后一般不用再 curl）

### v1.3.11
- 修复：用户「⋯」菜单被表格裁切遮挡；靠近底部时向上展开

### v1.3.10
- 面板用户状态显示「最后在线」时间

### v1.3.9
- 修复：Caddy 无法读取 hy2-aio.caddy（umask 077 导致 permission denied）
- repair 提前安装 hy2 CLI，避免 Caddy 失败后命令不存在

### v1.3.8
- 修复：SHA256SUMS 在 Windows 下 CRLF 导致 repair 校验失败
- fetch_modules 兼容 CRLF 校验文件

### v1.3.7
- 修复：只下载 `hy2.sh` 时 `repair` 无法拉模块 / 装不上 `hy2` 命令
- `repair` 会同步安装 `modules/` 与 `/usr/local/sbin/hy2`

### v1.3.6
- 中文分步安装向导：一路回车即可装完；结束前汇总确认
- Clash 订阅 `keepalive: 5s`；服务端默认 QUIC 保活
- 混淆可开关：`hy2 obfs on|off|show`，服务端/订阅/直链同步；默认开启
- 代理 UDP 默认改为 `8443`（云厂商更稳）；云防火墙提示跟随实际端口
