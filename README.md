# QQ 官方机器人 — Minecraft 服务器查询

基于 `qq-botpy` SDK 的 QQ 官方机器人，移植自 NoneBot2 项目。

## 功能

| 命令 | 说明 |
|------|------|
| `@Bot list` | 查询全部 MC 服务器状态（在线/延迟/玩家） |
| `@Bot 视奸` | 查看各服在线玩家 |
| `@Bot ip` | 服务器延迟一览 |
| `@Bot status` | 宿主机 CPU/内存/磁盘/运行时长 |
| `@Bot 服务器地图` | 地图和文档链接 |
| `@Bot 指令帮助` | 命令帮助 |
| `@Bot /执行 <实例> <命令>` | MCSM 面板发命令（仅管理员） |
| `@Bot /开启 <实例>` | MCSM 开启实例（仅管理员） |
| `@Bot /停止 <实例>` | MCSM 停止实例（仅管理员） |
| `@Bot /终止 <实例>` | MCSM 终止实例（仅管理员） |

## 项目结构

```
qqmlcbot/
├── main.py              # 入口 + Bot Client + 命令路由
├── config.py            # 配置（AppID/Secret/MCSM/超级用户）
├── handlers/
│   ├── server_query.py  # list/视奸/ip/服务器地图
│   ├── host_status.py   # status 宿主机监控
│   └── mcsm_control.py  # MCSM 面板命令
├── utils/
│   └── mc_utils.py      # MC 服务器查询工具函数
├── scripts/
│   └── create_command_panel.py  # 创建指定群的指令面板（一次性执行）
├── .env                 # 环境变量（敏感信息，勿提交 Git）
├── requirements.txt     # Python 依赖
└── README.md
```

## 快速开始

### 1. 环境要求

- Python 3.8+
- 网络可访问 QQ 开放平台 WebSocket 服务

### 2. 安装依赖

```bash
cd D:\desktop\nonebot\qqmlcbot
pip install -r requirements.txt
```

### 3. 配置

编辑 `.env` 文件：

```env
QQ_BOT_APPID=102090462
QQ_BOT_SECRET=你的AppSecret
SUPERUSERS=QQ号1,QQ号2
# 创建指令面板的目标群 OpenID，多个值用英文逗号分隔
QQ_GROUP_OPENIDS=openid_group_001,openid_group_002
```

### 4. 启动

```bash
python main.py
```

成功启动后日志会显示 "机器人已上线！"。

### 5. 创建群聊指令面板（可选）


指令面板只需创建一次，不要放在机器人启动流程中重复调用。脚本使用 QQ OpenAPI 的 `POST /v2/panels` 接口创建面板。业务消息记录写入 `mlcbot.log`；`botpy.log` 仅记录 SDK 的连接和鉴权信息。QQ 公域机器人只会收到 **@机器人** 的群消息，普通群聊消息不会下发给机器人，也不会写入日志。

先在目标群中 `@机器人 list` 发送任意消息，再从 `mlcbot.log` 中复制对应的群 OpenID：

```text
[群消息] group=实际的group_openid user=... content=...
```

将该值填入 `.env` 的 `QQ_GROUP_OPENIDS` 后，先预览请求内容：

```bash
python scripts/create_command_panel.py --dry-run
```

确认无误后创建面板：

```bash
python scripts/create_command_panel.py
```

面板包含 `list`、`视奸`、`ip`、`status`、`服务器地图` 和 `指令帮助`。MCSM 管理指令不会显示在公共面板中。

## 测试方法

### 方式一：直接在 QQ 测试

1. 确保机器人在 [QQ 开放平台](https://q.qq.com/qqbot/) 已通过审核
2. 在开放平台「开发设置」中确保群聊和私聊能力已开启
3. 将机器人邀请到测试 QQ 群
4. 在群里 `@机器人 list` 测试

### 方式二：使用沙箱环境

1. 访问 [QQ 机器人管理后台](https://q.qq.com/qqbot/#/developer/developer-setting)
2. 在「沙箱环境」中添加测试群和测试用户
3. 沙箱中可不受审核限制测试所有功能

### 功能验证清单

- [ ] `@Bot list` — 返回 4 个服务器状态、延迟、玩家
- [ ] `@Bot 视奸` — 返回各服在线玩家
- [ ] `@Bot ip` — 返回各服延迟
- [ ] `@Bot status` — 返回宿主机 CPU/内存/磁盘/运行时长
- [ ] `@Bot 服务器地图` — 返回地图和文档链接
- [ ] `@Bot /开启 scf` — MCSM 开启实例（超级用户）
- [ ] `@Bot /执行 scf list` — MCSM 发命令（超级用户）
- [ ] `@Bot /停止 scf` — MCSM 停止实例（超级用户）
- [ ] `@Bot 指令帮助` — 显示帮助
- [ ] 非超级用户执行 MCSM 命令被拒绝

### 模拟测试（无需 QQ）

可以单独测试工具函数，在 Python 交互环境中：

```python
import asyncio
from utils.mc_utils import get_status, get_players

# 测试连接 MC 服务器
status = asyncio.run(get_status("127.0.0.1:25566"))
if status:
    print(f"在线人数: {status.players.online}")
    print(f"延迟: {status.latency:.2f}ms")
    print(f"玩家: {get_players(status)}")
```

## 注意事项

1. **服务器图标**：QQ 官方 bot 群聊消息不支持直接嵌入 base64 图片，当前版本使用纯文字展示
2. **服务器连通性**：确保机器人所在主机能访问目标 MC 服务器端口
3. **MCSM 面板**：需要机器人所在主机能访问 `127.0.0.1:23333`（同机部署）
4. **API 密钥**：`.env` 已在 `.gitignore` 中，切勿将 Secret 提交到 Git
