# QQ 官方机器人 — Minecraft 服务器查询

基于 `qq-botpy` SDK 的 QQ 官方机器人，移植自 NoneBot2 项目。

## 功能

| 命令 | 说明 |
|------|------|
| `@Bot list` | 查看各服连接域名、在线人数和玩家名称 |
| `@Bot 视奸` | 查看各服在线人数和玩家名称 |
| `@Bot ip` | 查看各服连接域名 |
| `@Bot status` | 宿主机 CPU/内存/磁盘/运行时长 |
| `@Bot 服务器地图` | 地图和文档链接 |
| `@Bot oopz` / `@Bot kook` | OOPZ 和 KOOK 群邀请链接 |
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
├── logs/                # 机器人运行日志（启动时自动创建）
├── bot_client.py        # QQ 事件适配与跨功能消息编排
├── config.py            # 配置（AppID/Secret/MCSM/Gitee/超级用户）
├── handlers/
│   ├── command_router.py # 保留的文本命令路由入口
├── features/            # 按业务功能拆分的模块
│   ├── agent/            # AI 对话与服务器工具
│   ├── commands/         # 命令文本清洗和标准化
│   ├── fishing/          # 钓鱼命令、会话和按钮处理
│   ├── gitee_notifications/ # Gitee Push 轮询与群通知
│   ├── interactions/     # 跨功能按钮回调总分发
│   ├── mcsm_control/     # MCSM 实例控制命令
│   ├── muzzle/           # 抽奖、自助禁言和禁言按钮
│   ├── oopz/             # OOPZ 与 KOOK 邀请链接
│   ├── poll/              # 投票命令、存储流程和按钮处理
│   ├── security/         # 权限校验
│   └── server/            # Minecraft 查询与宿主机状态
├── external_tools/       # 外部平台、服务和存储适配器
│   ├── gitee/             # Gitee REST API
│   ├── mcsm/              # MCSM API
│   ├── minecraft/         # Minecraft 状态查询
│   ├── qq/                # QQ API 与 botpy 兼容适配
│   ├── storage/           # SQLite 投票仓库和群消息上下文
│   └── tencent_sheet/     # 腾讯在线表格读取
├── presentation/         # 回复文案、Markdown、键盘和模板
│   ├── templates/         # 所有 Markdown 回复模板，按功能分类
│   │   ├── messages/      # 通用、Agent、服务器、投票等回复
│   │   ├── help.md
│   │   ├── lottery_prompt.md
│   │   └── server_map.md
│   ├── keyboard.py       # QQ 内联键盘构造
│   ├── markdown.py       # Markdown 消息格式化
│   ├── messages.py       # 统一从模板渲染回复
│   └── reply_payload.py  # 命令回复载荷构造
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
# 社群邀请链接
OOPZ_INVITE_URL=https://oopz.cn/i/lA2eHI
KOOK_INVITE_URL=https://kook.top/W0Fa5D
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
# 可选：非敏感的服务器实例、目录和启动方式说明；内容会随 agent 自动回复请求发送给云端 API
AGENT_SERVER_CONTEXT=例如：生存服目录=/srv/minecraft/survival；由 systemd 服务 minecraft-survival 启动
# 可选：将模型原始响应写入 logs/mlcbot.log；可能包含工具调用参数，排查完成后建议关闭
AGENT_LOG_MODEL_RESPONSE=false
# Gitee 公开 Push 提交通知；用户名、群 OpenID 均用英文逗号分隔
GITEE_USERS=your-gitee-login
GITEE_NOTIFY_GROUPS=openid_group_001
GITEE_TOKEN=
GITEE_POLL_INTERVAL=60
GITEE_REQUEST_TIMEOUT=20
GITEE_MAX_COMMITS=10
```

Gitee 监听仅处理配置用户本人发起的公开 Push。`GITEE_NOTIFY_GROUPS` 填 QQ 群 OpenID；通知会回复该群最近五分钟内收到的消息。没有可用消息时通知会暂存，等群内有新消息后再发送。单条群消息最多作为 5 条被动回复的锚点；达到上限后队列会等待新的群消息。队列保存在进程内存中，重启后清空。每个群每分钟最多发送一条提交通知；冷却期间新发现的活动会跳过。`GITEE_TOKEN` 和 `GITEE_POLL_INTERVAL` 可选，轮询间隔最小为 5 秒。

回复目标只从机器人实际收到的群消息中选择。当前公域机器人默认只收到 @机器人的群消息；开启全量消息权限后，普通群消息也可作为回复目标。

全量接收模式开启后，群聊中未匹配到现有指令的普通消息有 20% 概率触发 Agent 自动回复；未匹配到指令的 @机器人消息会直接交给 Agent。Agent 会收到当前群最近十分钟的消息上下文；消息只保存在进程内存中，每群最多缓存 200 条、最多跟踪 64 个群，传给模型的上下文最多 40 条或 8,000 个字符。非超级用户可以使用普通对话，但服务器文件、目录和命令工具仍仅限 `SUPERUSERS`，服务器结构摘要也只会提供给超级用户。Agent 会收到项目根目录、代码模块职责、MCSM 地址和投票数据库路径等非敏感结构摘要；部署相关的实例名、目录和启动方式可通过 `AGENT_SERVER_CONTEXT` 补充。不要在该变量中填写密钥、令牌或其他认证信息，内容会发送到配置的云端模型。Agent 可读取文本文件、按行读取、列出目录、按文件名或内容搜索，并在服务器默认 shell 中执行命令。命令使用 bot 进程权限且不设命令白名单；单次最多运行 60 秒，返回输出最多 12,000 个字符。每个请求最多执行 8 次工具调用、最多进行 5 轮；网络或临时服务错误、响应格式错误最多重试 3 次，间隔为 1、2、4 秒。单个文件最多读取 64 KiB，文本搜索最多读取 2 MiB，并限制目录扫描量。工具定义会随每次请求发送。API 服务需支持 Chat Completions 工具调用，并可返回普通 JSON 或 SSE 流式响应。

排查模型返回时，可将 `AGENT_LOG_MODEL_RESPONSE` 设为 `true` 并重启 bot。原始模型响应会写入 `logs/mlcbot.log`，最多记录 64 KiB 字符；日志可能包含模型生成的命令、路径或回答内容，排查完成后请关闭该选项。

### 4. 启动

```bash
python main.py
```

成功启动后日志会显示 "机器人已上线！"。

### 5. 创建群聊指令面板（可选）


指令面板只需创建一次，不要放在机器人启动流程中重复调用。脚本使用 QQ OpenAPI 的 `POST /v2/panels` 接口创建面板。业务消息记录写入 `logs/mlcbot.log`；`logs/botpy.log` 仅记录 SDK 的连接和鉴权信息。QQ 公域机器人只会收到 **@机器人** 的群消息，普通群聊消息不会下发给机器人，也不会写入日志。

先在目标群中 `@机器人 list` 发送任意消息，再从 `logs/mlcbot.log` 中复制对应的群 OpenID：

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

面板包含现有查询命令、`oopz`、`kook`、`开始钓鱼`，以及 `投票` 和 `投票结果`。投票入口仍会在业务层校验 `SUPERUSERS`；MCSM 管理指令不会显示在公共面板中。

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

- [ ] `@Bot list` — 返回各服域名、在线人数和玩家名称
- [ ] `@Bot 视奸` — 返回各服在线人数和玩家名称
- [ ] `@Bot ip` — 返回各服连接域名
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
from external_tools.minecraft.status_client import get_status, get_players

# 测试连接 MC 服务器
status = asyncio.run(get_status("127.0.0.1:25566"))
if status:
    print(f"在线人数: {status.players.online}")
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
