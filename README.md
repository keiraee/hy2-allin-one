# HY2 AIO v1.3.2

一键部署 Hysteria 2 + 多用户订阅 + 轻量面板

## 快速开始

```bash
# 下载并安装
curl -fsSL https://raw.githubusercontent.com/keiraee/hy2-allin-one/main/hy2.sh -o hy2.sh
sudo bash hy2.sh install
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

## 目录结构

```
hy2-allin-one/
├── hy2.sh              # 入口脚本
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

## 更新日志

### v1.3.2
- 修复 Clash 订阅中 `nameserver` 缩进错误，确保自定义 DNS 正常生效
- 自动将 HY2 服务器公网 IPv4 排除出 TUN 路由，避免全局模式下连接自身形成回环和间歇性超时

### v1.3.1
- 前端支持给用户添加设备备注（如 iPhone 13、笔记本）
- 前端支持直接禁用/启用用户，禁用后立即无法连接，数据保留
- 禁用用户的订阅地址返回 403

### v1.3.0
- 重构为模块化架构
- 新增交互式菜单
- 命令简化为 `hy2`
- 支持多种 Linux 发行版
