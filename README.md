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
| `@Bot /抽奖` | 创建 0–30 分钟随机禁言抽奖按钮（仅管理员） |
| `@Bot /开始钓鱼` | 开始钓鱼小游戏，鱼上钩后需在 2 秒内拉钩 |
| `@Bot /自助口球` | 随机禁言自己 1–60 分钟（仅群聊） |
| `@Bot /投票` | 从腾讯在线表格选择科技、冒险或混合候选项并发起投票（仅管理员） |
| `@Bot /投票结果` | 查看本群当前投票结果（仅管理员） |

## 项目结构

```
qqmlcbot/
├── main.py              # 日志配置与启动入口
├── bot_client.py        # QQ 事件适配层
├── config.py            # 配置（AppID/Secret/MCSM/超级用户）
├── handlers/
│   ├── server_query.py  # list/视奸/ip/服务器地图
│   ├── host_status.py   # status 宿主机监控
│   ├── mcsm_control.py  # MCSM 面板命令
│   ├── lottery.py       # 抽奖与群成员禁言
│   ├── group_mute.py    # QQ 群成员禁言接口
│   ├── self_muzzle.py   # 自助口球命令
│   ├── poll.py          # 投票命令与结果查询
│   ├── command_router.py # 命令路由
│   └── interaction.py   # 按钮回调处理
├── utils/
│   ├── mc_utils.py      # MC 服务器查询工具函数
│   ├── command_text.py  # 命令文本清洗
│   ├── messages.py      # 统一回复文案与 Markdown 格式化
│   ├── permissions.py   # 超级用户鉴权
│   ├── poll_store.py    # SQLite 投票状态与计票
│   ├── tencent_sheet.py # 腾讯在线表格候选项读取
│   └── reply_payload.py # Markdown 与键盘回复载荷
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
conda env create -f environment.yml
conda run -n mlcqqbot python main.py
```

### 3. 配置

编辑 `.env` 文件：

```env
QQ_BOT_APPID=102090462
QQ_BOT_SECRET=你的AppSecret
SUPERUSERS=QQ号1,QQ号2
# 创建指令面板的目标群 OpenID，多个值用英文逗号分隔
QQ_GROUP_OPENIDS=openid_group_001,openid_group_002
# 投票候选项来源；下面是当前“整合包收集”表格的默认值，可按需覆盖
TENCENT_SHEET_URL=https://docs.qq.com/sheet/DUU5xSWRCR2VZdkhO?tab=BB08J2
TENCENT_ADVENTURE_TAB=BB08J2
TENCENT_TECHNOLOGY_TAB=g9hsny
# 可选；默认保存在项目 data 目录中
POLL_DB_PATH=D:\desktop\bot\mlcqqbot\data\polls.sqlite3
# 云端 AI 助手；API 需兼容 OpenAI Chat Completions 工具调用格式
AGENT_API_URL=https://api.example.com/v1/chat/completions
AGENT_API_KEY=你的云端API密钥
AGENT_MODEL=你的模型名称
# 可选：非敏感的服务器实例、目录和启动方式说明；内容会随 /agent 请求发送给云端 API
AGENT_SERVER_CONTEXT=例如：生存服目录=/srv/minecraft/survival；由 systemd 服务 minecraft-survival 启动
```

`/agent <问题>` 仅供 `SUPERUSERS` 使用。Agent 会收到项目根目录、代码模块职责、MCSM 地址和投票数据库路径等非敏感结构摘要；部署相关的实例名、目录和启动方式可通过 `AGENT_SERVER_CONTEXT` 补充。不要在该变量中填写密钥、令牌或其他认证信息，内容会发送到配置的云端模型。Agent 可读取文本文件、按行读取、列出目录、按文件名或内容搜索，并在服务器默认 shell 中执行任意命令。命令使用 bot 进程权限且不设命令白名单；单次最多运行 60 秒，返回输出最多 12,000 个字符。每轮最多调用五个工具，单个文件最多读取 64 KiB；文本搜索最多读取 2 MiB，并限制目录扫描量。工具定义会随每次请求发送，普通闲聊不会自动调用工具。API 服务需支持 Chat Completions 工具调用。

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

面板包含现有查询命令、`开始钓鱼`，以及 `投票` 和 `投票结果`。投票入口仍会在业务层校验 `SUPERUSERS`；MCSM 管理指令不会显示在公共面板中。

### 6. 群聊投票

管理员发送 `/投票` 后选择候选来源：

- `科技`：读取“科技包”子表第二行起的第一列
- `冒险`：读取“冒险包”子表第二行起的第一列
- `混合`：合并科技与冒险候选项并去重

候选项会在正文中按编号完整列出，按钮显示编号。群友可以先点击多个候选项（点击后显示勾选标记），再次点击可取消；最后点击末行的“提交投票”按钮才会正式计票，并在群内提示投票人和包名。QQ 单条键盘最多容纳 25 个按钮，因此最多支持 24 个候选项；按当前设计不分页，超过上限时会拒绝发起并提示整理表格。投票保存在 SQLite 中，机器人重启后仍可通过 `/投票结果` 查询。

腾讯表格只需要分享链接具有查看权限；本项目不会使用或保存腾讯文档账号、Cookie、`access_token` 或 `open_id`。读取失败时会在进程内使用最近一次成功读取的缓存。

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
- [ ] `@Bot /抽奖` — 管理员创建抽奖按钮，群成员点击后随机禁言 0–30 分钟
- [ ] `@Bot /自助口球` — 随机禁言自己 1–60 分钟
- [ ] `@Bot /投票` — 管理员选择类别后生成候选项编号按钮
- [ ] 群成员可先勾选多个编号、修改选择，点击提交后正式计票
- [ ] `@Bot /投票结果` — 管理员查看候选项票数和占比

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
5. **群管理权限**：抽奖禁言依赖 QQ 群管理接口，机器人需要具备群管理员权限；群主、管理员和机器人账号不能被该接口禁言
6. **投票候选项上限**：QQ 单条内联键盘最多放置 25 个按钮（含提交按钮），因此最多 24 个候选项；本项目不会为超限候选项自动分页
7. **腾讯表格权限**：候选表必须允许通过分享链接查看；无需在配置中保存腾讯文档访问令牌
