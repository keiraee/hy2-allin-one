# HY2 AIO

一键部署 Hysteria 2 + 多用户订阅 + 轻量 Web 面板（512MB 小机友好）。

**稳定版**见 [Releases](https://github.com/keiraee/hy2-allin-one/releases)（含版本说明与变更记录）。  
跟踪最新开发版：`HY2_REPO_REF=main`。

## 快速开始

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v1.3.5/hy2.sh -o hy2.sh
sudo bash hy2.sh install
```

## 已安装 · 升级

```bash
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/v1.3.5/hy2.sh -o hy2.sh
sudo bash hy2.sh repair
```

`repair` 会打回滚快照、更新模块与配置、重启面板后端；**不会重启 Hysteria**，现有连接一般不受影响。

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
| `HY2_BACKUP_DAYS` | 备份保留天数 | 14 |
| `HY2_RATE_LIMIT_SUBSCRIPTION` | 订阅 `/s/` 每 IP 每分钟上限 | 30 |
| `HY2_RATE_LIMIT_API` | 面板 API 每 IP 每分钟上限 | 120 |
| `HY2_REPO_REF` | 模块 Git ref | `v1.3.5` |
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

- **整机流量**：面板顶部为网卡计数，尽量对齐云厂商套餐；Clash 订阅进度与此同源。
- **用户流量**：用户表为 HY2 代理分摊参考，各用户之和通常小于整机。
- **凭据**：密码/订阅 token 不在 `data.json` 公开；面板内按需复制。
- **备份**：敏感备份仅 CLI，不放在 Web 可下载目录。
