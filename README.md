# HY2 AIO v1.4.0

一键部署 Hysteria 2 + 多用户订阅 + 轻量 Web 面板（512MB 小机友好）。

**稳定版**见 [Releases](https://github.com/keiraee/hy2-allin-one/releases)（含版本说明与变更记录）。  
想先试用仓库 `main` 上还没发版的功能，见下方 [试用 main 开发版](#试用-main-开发版)。

## 快速开始

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v1.4.0/hy2.sh -o hy2.sh
sudo bash hy2.sh install
```

按中文提示一步步回车即可（公网 IP → 端口 → 面板端口 → 用户数 → 流量 → 域名/伪装）。  
一路回车使用推荐默认值；高级用户也可用环境变量无人值守安装（见下方）。

## 已安装 · 升级

跟 GitHub 最新正式版（Release）：

```bash
# 需 root：已是 root 直接执行；有 sudo 再加 sudo
hy2 upgrade
hy2 restart
```

`upgrade` / `repair` 会打回滚快照、更新模块与配置、写入 Hysteria 配置（含 QUIC 保活）；**默认不重启 Hysteria**。使配置生效请 `sudo hy2 restart`，或用 `sudo hy2 obfs on|off`（会重启 Hysteria）。

## 试用 main 开发版

`main` 是仓库最新提交，**不是 Release**，可能比当前正式版多功能，也可能还不稳定。第一次必须带 `HY2_REPO_REF=main`，本机会写入 `HY2_TRACK_REF=main`；之后普通 `hy2 upgrade` 会继续跟 `main`，不会被后续正式版 tag 带跑。升级会先向 GitHub API 解析当前 commit，再按 SHA 下载 `SHA256SUMS` 和模块，避免 `raw.githubusercontent.com/main/` 把旧校验文件缓存住、面板不刷新。

已安装，强制切到 / 更新 `main`：

```bash
sudo HY2_REPO_REF=main hy2 upgrade
sudo hy2 restart
```

本机还没有 `hy2`，或旧版 `hy2 upgrade` 一直提示已是最新、实际没拉到 `main`：

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/main/hy2.sh -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh upgrade
sudo hy2 restart
```

若升级日志没有 `钉住提交`、或面板仍是旧界面，说明 `main` 的 raw 缓存还没刷新。改用当前 commit 拉引导脚本：

```bash
sha=$(curl -fsSL https://api.github.com/repos/keiraee/hy2-allin-one/commits/main | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])')
curl -fsSL "https://raw.githubusercontent.com/keiraee/hy2-allin-one/${sha}/hy2.sh" -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh upgrade
sudo hy2 restart
```

全新安装也直接用 `main`：

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/main/hy2.sh -o hy2.sh
sudo HY2_REPO_REF=main bash hy2.sh install
```

记住轨道之后，日常更新：

```bash
sudo hy2 upgrade
sudo hy2 restart
```

切回 GitHub 正式版：

```bash
sudo HY2_REPO_REF=latest hy2 upgrade
sudo hy2 restart
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
sudo hy2 update              # 更新 Hysteria
sudo hy2 uninstall           # 卸载
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
| `HY2_TOTAL_TB` | 套餐流量 TB | 1 |
| `HY2_PANEL_USER` | 面板用户名 | admin |
| `HY2_PANEL_PASS` | 面板密码 | 随机生成 |
| `HY2_PANEL_PATH` | 面板路径 | 随机生成 |
| `HY2_SNI` | 客户端 SNI | www.amazon.sg |
| `HY2_OBFS` | Salamander 混淆 `0/1` | `1`（开） |
| `HY2_PORT` | Hysteria UDP 端口 | 安装向导默认 `8443` |
| `HY2_BACKUP_DAYS` | 备份保留天数 | 14 |
| `HY2_RATE_LIMIT_SUBSCRIPTION` | 订阅 `/s/` 每 IP 每分钟上限 | 30 |
| `HY2_RATE_LIMIT_API` | 面板 API 每 IP 每分钟上限 | 120 |
| `HY2_REPO_REF` | 模块 Git ref；`upgrade` 空值=已记住的 `HY2_TRACK_REF` 或 latest | install 默认 `v1.4.0` |
| `HY2_CLIENT_INSECURE` | 客户端 skip-cert-verify | sslip/IP 默认 true |
| `HYSTERIA_VERSION` | Hysteria 版本 | `v2.12.1` |
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

- **Clash 订阅**默认 `mode: rule`（国内直连、其余走 HY2）及 `keepalive: 5s`；服务端写入 QUIC `keepAlivePeriod: 5s`、`maxIdleTimeout: 120s`。
- **混淆默认开启**；不稳时可 `sudo hy2 obfs off` 后让客户端更新订阅（关闭的是伪装，不是加密）。
- **安装向导**默认代理 UDP `8443`（云上比 443 更稳）；仍可改成 `443`。
- **整机流量**：面板顶部为网卡计数，尽量对齐云厂商套餐；Clash 订阅进度与此同源。
- **用户流量**：用户表为 HY2 代理分摊参考，各用户之和通常小于整机。
- **凭据**：密码/订阅 token 不在 `data.json` 公开；面板内按需复制。
- **备份**：敏感备份仅 CLI，不放在 Web 可下载目录。

## 更新日志

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
