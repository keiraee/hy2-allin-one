# HY2 AIO v1.3.17

一键部署 Hysteria 2 + 多用户订阅 + 轻量 Web 面板（512MB 小机友好）。

**稳定版**见 [Releases](https://github.com/keiraee/hy2-allin-one/releases)（含版本说明与变更记录）。  
跟踪最新开发版：`HY2_REPO_REF=main`。

## 快速开始

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v1.3.17/hy2.sh -o hy2.sh
sudo bash hy2.sh install
```

按中文提示一步步回车即可（公网 IP → 端口 → 面板端口 → 用户数 → 流量 → 域名/伪装）。  
一路回车使用推荐默认值；高级用户也可用环境变量无人值守安装（见下方）。

## 已安装 · 升级

```bash
# 需 root：已是 root 直接执行；有 sudo 再加 sudo
hy2 upgrade
hy2 restart
```

若本机还没有 `hy2 upgrade`（很旧的安装），先执行一次：

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v1.3.17/hy2.sh -o hy2.sh
sudo bash hy2.sh repair
```

`upgrade` / `repair` 会打回滚快照、更新模块与配置、写入 Hysteria 配置（含 QUIC 保活）；**默认不重启 Hysteria**。使配置生效请 `sudo hy2 restart`，或用 `sudo hy2 obfs on|off`（会重启 Hysteria）。

## 使用方法

### 交互菜单

```bash
sudo hy2
```

### 命令模式

```bash
sudo hy2 status              # 查看状态
sudo hy2 show                # 显示账号
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
| `HY2_REPO_REF` | 模块 Git ref | `v1.3.17` |
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

- **Clash 订阅**默认 `keepalive: 5s`；服务端写入 QUIC `keepAlivePeriod: 5s`、`maxIdleTimeout: 120s`。
- **混淆默认开启**；不稳时可 `sudo hy2 obfs off` 后让客户端更新订阅（关闭的是伪装，不是加密）。
- **安装向导**默认代理 UDP `8443`（云上比 443 更稳）；仍可改成 `443`。
- **整机流量**：面板顶部为网卡计数，尽量对齐云厂商套餐；Clash 订阅进度与此同源。
- **用户流量**：用户表为 HY2 代理分摊参考，各用户之和通常小于整机。
- **凭据**：密码/订阅 token 不在 `data.json` 公开；面板内按需复制。
- **备份**：敏感备份仅 CLI，不放在 Web 可下载目录。

## 更新日志

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
