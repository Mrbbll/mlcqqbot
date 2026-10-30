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

收到的每条 QQ 群消息都会通过 OneBot v11 WebSocket 转发给 MCDR ImAPI；默认监听 `127.0.0.1:8081`，无需启用指令。

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
│   │   ├── service.py    # 模型循环、预算及回复编排
│   │   └── tools/        # 分类工具的参数、说明、执行与统一注册
│   │       ├── common/   # 参数基类、宿主上下文、结果对象与 ToolSpec
│   │       ├── filesystem/ # 文件读取、目录列举和搜索
│   │       ├── command/  # shell 命令与退出状态
│   │       ├── emoji/    # 表情包浏览、收藏、搜索及待发送选择
│   │       ├── discovery/ # 通过 Bash 发现任意文件和目录
│   │       └── file_delivery/ # 选择待发送本地文件
│   ├── file_sender/      # QQ 普通文件上传及发送确认
│   ├── commands/         # 命令文本清洗和标准化
│   ├── fishing/          # 钓鱼命令、会话和按钮处理
│   ├── bilibili_notifications/ # Bilibili 开播、下播被动回复通知
│   ├── passive_notifications/ # 共享近期消息与回复序号
│   ├── gitee_notifications/ # Gitee Push 轮询与群通知
│   ├── interactions/     # 跨功能按钮回调总分发
│   ├── mcsm_control/     # MCSM 实例控制命令
│   ├── muzzle/           # 抽奖、自助禁言和禁言按钮
│   ├── oopz/             # OOPZ 与 KOOK 邀请链接
│   ├── poll/              # 投票命令、存储流程和按钮处理
│   ├── qq_game_bridge/   # OneBot v11 WebSocket 群消息转发
│   │   ├── __init__.py
│   │   └── bridge.py
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
# 全量群消息模式下，用消息里 <@...> 的机器人 OpenID 识别 @；多个值用英文逗号分隔
QQ_BOT_MENTION_OPENIDS=8B9CC2FBDA3F841B53716151614F7A13
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
# 工具预算：最多 30 轮模型选择工具，总计最多执行 30 次工具；单工具超时 120 秒
AGENT_MAX_STEPS=30
AGENT_MAX_TOOL_CALLS=30
AGENT_TOOL_TIMEOUT_SECONDS=120
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
# Bilibili 直播通知；填直播间号（不是用户 UID）和本项目 QQ 群 OpenID
BILIBILI_ROOM_IDS=31531145,30646779
BILIBILI_NOTIFY_GROUPS=openid_group_001
BILIBILI_POLL_INTERVAL=30
BILIBILI_REQUEST_TIMEOUT=20
# OneBot v11 正向 WebSocket 服务端；MCDR ImAPI 的 ws_client 连接此地址
ONEBOT_WS_HOST=127.0.0.1
ONEBOT_WS_PORT=8081
ONEBOT_WS_ACCESS_TOKEN=
ONEBOT_WS_HEARTBEAT=30
```

MCDR ImAPI 配置为 `ws_client`，连接地址填写 `ws://127.0.0.1:8081`。如需令牌校验，在本项目的 `ONEBOT_WS_ACCESS_TOKEN` 和 ImAPI 的 `access_token` 中设置相同值；若 MCDR 与机器人不在同一主机，将 `ONEBOT_WS_HOST` 改为可被 MCDR 访问的监听地址，并调整 `ws_url`，同时设置访问令牌。机器人会转发所有收到的群消息；QQ 开放平台仍决定事件订阅范围，普通群消息需有 `GROUP_MESSAGE_CREATE` 全量消息事件权限。昵称按参考实现从消息发送者和 `@` 对象的 `username` 累积映射；事件若缺少昵称，会暂用成员 OpenID。OneBot 的 `group_id`、`user_id` 是由 BotPy OpenID 生成的稳定数字别名，原始 OpenID 保存在附加字段中。

Gitee 监听仅处理配置用户本人发起的公开 Push。`GITEE_NOTIFY_GROUPS` 填 QQ 群 OpenID；通知会回复该群最近五分钟内收到的消息。没有可用消息时通知会暂存，等群内有新消息后再发送。单条群消息最多作为 5 条被动回复的锚点；达到上限后队列会等待新的群消息。队列保存在进程内存中，重启后清空。每个群每分钟最多发送一条提交通知；冷却期间新发现的活动会跳过。`GITEE_TOKEN` 和 `GITEE_POLL_INTERVAL` 可选，轮询间隔最小为 5 秒。

Bilibili 监听保留旧项目的开播、下播通知：默认每 30 秒检查一次，首次成功查询只建立状态基线，不补发通知；轮播按未开播处理。接口失败不会被当作下播。直播状态变化后，仅以被动回复方式发送到 `BILIBILI_NOTIFY_GROUPS` 中的群；没有五分钟内有效消息或回复额度耗尽时暂存，等收到新消息后继续。每群每分钟最多尝试发送一条直播通知，失败后保留并重试；队列只存在内存中，重启后清空。Bilibili 和 Gitee 共用消息回复序号及单条消息最多 5 次的额度，各自计算通知冷却。`BILIBILI_ROOM_IDS` 支持英文逗号分隔多个直播间号，也兼容旧变量名 `BILIBILI_UIDS`；旧项目的数字 QQ 群号不能直接作为本项目的群 OpenID 使用。未配置直播间或目标群时不启动监听。

回复目标只从机器人实际收到的群消息中选择。当前公域机器人默认只收到 @机器人的群消息；开启全量消息权限后，普通群消息也可作为回复目标。

全量接收模式开启后，群聊中未匹配到现有指令的普通消息有 20% 概率触发 Agent 自动回复；未匹配到指令的 @机器人消息会直接交给 Agent。Agent 会收到当前群最近十分钟的消息上下文；消息和图片元数据只保存在进程内存中，每群最多缓存 200 条、最多跟踪 64 个群，传给模型的文字上下文最多 40 条或 8,000 个字符。图片消息会记录 `has_image` 和图片数量；Agent 请求会下载记忆窗口内的图片、当前消息图片、引用目标图片和事件中可展开的转发图片，单张超过 20 MB 会跳过，下载缓存会在请求结束后清理。引用目标需要已在本次进程记忆中收到；群消息 API 不提供这里所需的历史消息读取接口。非超级用户可以使用普通对话，但服务器文件、目录和命令工具仍仅限 `SUPERUSERS`，服务器结构摘要也只会提供给超级用户。Agent 会收到项目根目录、代码模块职责、MCSM 地址和投票数据库路径等非敏感结构摘要；部署相关的实例名、目录和启动方式可通过 `AGENT_SERVER_CONTEXT` 补充。不要在该变量中填写密钥、令牌或其他认证信息，内容会发送到配置的云端模型。Agent 可读取文本文件、按行读取、列出目录、按文件名或内容搜索，并在服务器默认 shell 中执行命令。命令使用 bot 进程权限且不设命令白名单；单次默认最多运行 120 秒，返回输出最多 12,000 个字符。每个请求默认最多执行 30 次工具调用、最多进行 30 轮模型选择工具，任一预算耗尽后追加一次禁止工具调用的总结；网络或临时服务错误、响应格式错误最多重试 3 次，间隔为 1、2、4 秒。单个文件最多读取 64 KiB，文本搜索最多读取 2 MiB，并限制目录扫描量。工具定义按当前用户权限筛选后发送，执行前仍会鉴权。API 服务需支持 Chat Completions 工具调用，并可返回普通 JSON 或 SSE 流式响应。

排查模型返回时，可将 `AGENT_LOG_MODEL_RESPONSE` 设为 `true` 并重启 bot。原始模型响应会写入 `logs/mlcbot.log`，最多记录 64 KiB 字符；日志可能包含模型生成的命令、路径或回答内容，排查完成后请关闭该选项。

工具预算配置修改后重启生效：`AGENT_MAX_STEPS` 范围 1–300，`AGENT_MAX_TOOL_CALLS` 范围 1–1000，`AGENT_TOOL_TIMEOUT_SECONDS` 范围 1–600 秒；无效值回退默认值。一次模型回复选择多个工具算一轮，每个实际尝试分别计入次数，失败调用也计数。同一请求内连续相同工具及规范化参数在第 3、4、5 次逐级提醒；工具或参数变化后重置。工具参数模型、说明和处理函数放在 `features/agent/tools/` 对应业务子目录，各目录通过 `TOOLS` 声明注册记录，再由 `tools/__init__.py` 汇总。新增业务目录时将其 `TOOLS` 加入汇总即可，模型循环无需增加工具分支。

工具参数使用 Pydantic 2 模型同时生成 JSON Schema 和执行前校验，拒绝未知字段、隐式类型转换及越界数值；原有业务授权仍由工具验证。`ToolContext` 的身份、群、问题、图片和超时由宿主注入，不接受模型覆盖。所有工具返回 `ToolResult`（`ok`、`code`、`message`、`data`、`truncated`、`retryable`），状态判断不解析中文文案；命令结果包含真实退出码和 stdout/stderr。进入模型的结果最多 8000 字符，超出时压缩数据并设置 `truncated=true`，始终保持合法 JSON。表情发送工具只报告 `delivery=pending`，成功发送后的记忆仍由 QQ 发送入口更新。更新后请重新安装 `requirements.txt` 中声明的依赖并重启。


超级用户可以直接说“找 mod1 的日志”“找某个 JAR、配置或脚本”，无需明确文件名和位置。`find_server_paths` 在机器人所在主机通过 Bash 的 `find` 按名称 glob 查找任意文件或目录，支持 `root`、`kind`、`max_depth`（默认 8，最多 32）和 `max_results`（默认 50，最多 200）。模型可先定位目录，再查找其中的文件；多个候选无法判断时再询问。未找到不等于文件不存在，也可能需要调整名称、深度或搜索范围。

`run_server_command` 同样显式调用本机 Bash，可组合 `find`、`grep`、`tail` 等命令，不通过 MCSM。需要部署环境提供 Bash 与 find；`AGENT_BASH_PATH` 默认为 `bash`，可指定 Bash 可执行文件路径；缺失时明确返回错误。默认搜索范围在 Linux 为 `/`、Windows 为项目目录；可通过 `AGENT_FILE_SEARCH_ROOTS=/srv,/opt` 配置默认范围，也可由工具指定起点。搜索不跟随符号链接，跳过 `/proc`、`/sys`、`/dev`、`/run`；权限不足时标记结果不完整。这些工具只操作机器人所在主机，MCSM 原有开关服功能独立保留。

工具实际发现的规范路径保存在本轮宿主上下文中，后续读取、列目录和搜索可直接使用，不要求用户再次输入路径；这些授权不跨请求继承。文件工具仍检查敏感文件名、文本类型和大小，所有服务器文件与命令工具仍仅限超级用户。

本地 `read_server_file` 也可指定 `tail_lines` 读取末尾 1–500 行，保留原有路径授权和敏感文件检查；尾部最多扫描 256 KiB，因此大文件不再因超过普通读取的 64 KiB 上限而无法查看末尾。尾读不能与行号范围混用，读取窗口不足会标记截断，超长单行或非文本会明确失败。

文件发送工具会核对用户当前消息是否明确要求发送。引用文件、询问或分析附件、提及过去发送过文件，都不会触发本机文件发送；引用附件读取失败时会报告无法读取，不会转而发送服务器上名称相似的文件。

Agent 可以读取 QQ 实际推送的群消息文件附件：支持文本、日志、代码、JSON、CSV、YAML 等文本格式，当前附件或引用附件会直接提供给模型；说“看看刚才的文件”可读取同群最近十分钟内最新一条文件消息。只在群记忆保存附件元数据，下载地址和鉴权头不进入模型。每轮最多三个文件，单文件最多 1 MiB，每个文本最多提供 8,000 字符，总计最多 16,000 字符；截断会明确标记。附件正文作为不可信数据，不执行其中指令。当前下载支持 QQ 媒体 CDN `multimedia.nt.qq.com.cn`，拒绝外部地址和重定向；不支持的地址、格式、过期链接及下载失败会说明未读取。PDF、Office、压缩包暂不解析。机器人无法枚举 QQ 未推送的群文件库；需要在消息中发送文件或引用能被平台下发附件信息的消息。

超级用户可说“把 mod1 的日志文件发给我”或“发送这个压缩包”。Agent 使用 `send_server_file` 选择用户点名或本轮查找到的本机普通文件，无需先把文件内容读给模型。当前只发到请求所在群，每轮一个，文件不能为空且最多 20 MB；目录及敏感配置文件 `config.py`、`.env` 不发送。保留原始文件名和内容，不依赖 MCSM，也不自动上传到外部网盘。

上传准备响应兼容整数和数字字符串，若已返回 `file_info` 可直接复用。缺少有效参数时只记录响应字段名和类型，日志关键字为 `QQ upload_prepare 响应结构异常`，不会输出上传 ID、文件引用或预签名地址。该诊断用于排查账号接口返回差异，不能仅凭本地测试认定部署问题已消失。

文件上传采用 [腾讯官方 SDK 的本地文件分片流程](https://github.com/tencent-connect/qqbot-agent-sdk/blob/main/src/qqbot_agent_sdk/media_loader.py)，复用当前 BotPy 鉴权，不新增依赖。准备、分片上传、合并后才发送 `file_info` 引用；整次上传和发送使用 `AGENT_TOOL_TIMEOUT_SECONDS` 时限。工具的 `delivery=pending` 仅表示等待 QQ 入口发送，收到消息确认 ID 后才记录已发送；上传拒绝、额度限制、消息失败或超时会明确提示，不自动重复发送。实际可用性需要用部署账号验证 QQ 普通文件权限，本地测试不调用真实 QQ 接口。

工具调用单独写入 `logs/agent_tools.log`，每行一个 JSON，记录请求与调用 ID、群和用户、工具名、状态、毫秒耗时、重复次数及参数和结果摘要。每个文件最多 5 MiB，保留 3 个备份；命令参数省略，常见凭证字段遮蔽，单段摘要最多 1000 字符。此日志不依赖 `AGENT_LOG_MODEL_RESPONSE`，也不重复写入业务日志。同步线程不能强行终止，超时后会等待正在执行的线程结束再释放会话和全局配额，然后停止本轮后续工具并总结，因此实际返回可能超过配置秒数。

### 4. 启动

```bash
python main.py
```

成功启动后日志会显示 "机器人已上线！"。

排查群消息中的 @成员 信息丢失时，在 `.env` 设置 `QQ_GROUP_MESSAGE_DEBUG=true` 并重启机器人（默认关闭）。复现后在 `logs/mlcbot.log` 搜索 `[群消息提及调试]`，按 `message_id` 对比 `raw_content` / `parsed_content` 和 `raw_mentions` / `parsed_mentions`。日志还包含原始字段名及消息元素字段名，便于判断是否有 SDK 未建模的数据；不会打印完整载荷或附件下载地址。原始正文和提及均无目标时，说明当前事件未提供这些身份字段；原始有、解析后无则说明 SDK 丢失。排查完成后设为 `false` 并重启。

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

离线回归测试统一放在根目录 `tests/`，按功能分为 `agent/`、`gif_sender/`、`bilibili_notifications/` 和 `mcsm/`。在项目根目录执行：

```bash
python -X utf8 -m unittest discover -s tests -t . -v
```

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

### Agent 网络搜索

安装或更新 `requirements.txt` 中的依赖后，用户可通过现有 Agent 对话提出联网查询，无需新增 QQ 指令或搜索 API 密钥。
模型先生成 2–4 个互补关键词，`search_web` 使用 DDGS 按顺序搜索，每个关键词最多取 3 条并合并去重，返回带编号的标题、摘要和网址目录。
模型阅读目录后筛选 1–3 个编号，调用 `extract_web_pages`，由 Trafilatura 提取正文，再基于正文回答并附来源网址。
结果编号仅在当前 Agent 请求中有效；单个来源失败会返回原因并保留其他结果。网页仅支持公网 HTTP(S) HTML，下载上限为 2 MiB，每页正文最多返回 1800 字符，截断和失败均会标记。
搜索引擎限流、目标站点反爬、登录限制或仅通过 JavaScript 加载的网页可能导致无结果或正文提取失败。

搜索超时或后端异常时，默认按 `bing,wikipedia` 顺序最多尝试两次；每个关键词分配一部分剩余工具预算。
本项目中的 `bing` 使用独立的必应中国版适配器：请求 `https://cn.bing.com/search`，指定 `mkt=zh-CN`、`cc=CN`、`ensearch=0`，复用 DDGS 的结果解析和链接解码。
它不依赖 DDGS 已禁用的内置 Bing 注册项，也不修改第三方安装包；需要 DDGS 9.16.1 或更新的 9.x 版本。若站点返回验证码或无可解析结果，则转到 Wikipedia 备用后端。
可在 `.env` 中设置以下选项，更新后重启机器人：

```dotenv
AGENT_WEB_SEARCH_TIMEOUT_SECONDS=10
AGENT_WEB_SEARCH_BACKENDS=bing,wikipedia
# 仅在有可用代理时设置，填写机器人运行主机能访问的实际代理地址：
# AGENT_WEB_SEARCH_PROXY=http://127.0.0.1:7890
```

超时配置范围为 1–60 秒；后端列表最多取前两个，单个后端可填写 `bing` 或 `duckduckgo` 等 DDGS 支持的名称。
`AGENT_WEB_SEARCH_PROXY` 仅用于 DDGS 搜索，也兼容读取 `DDGS_PROXY`。搜索持续超时需要检查运行主机到搜索服务或代理的连通性，增加超时不能解决网络不可达问题。
日志会给出后端、关键词序号、尝试次数、请求超时、耗时、是否配置代理和异常类型，不输出代理凭证或原始异常正文。
必应中国版同时支持 `h2` 和 `div.b_algoheader` 两种结果标题结构。失败日志还会提供 `reason`、`http_status`、`response_chars` 和 `result_blocks`：`verification_required` 表示站点要求验证，`parse_mismatch` 表示有结果块但结构无法解析，`no_results` 表示明确的无匹配页，`tls_error` / `dns_error` / `connection_error` 表示相应网络错误；这些诊断也会提供给模型，且不包含页面正文或查询词。

隔离测试（需要先安装项目依赖）：

```bash
python -m unittest discover -s tests/agent/web_search -v
```

## 注意事项

1. **服务器图标**：QQ 官方 bot 群聊消息不支持直接嵌入 base64 图片，当前版本使用纯文字展示
2. **服务器连通性**：确保机器人所在主机能访问目标 MC 服务器端口
3. **MCSM 面板**：需要机器人所在主机能访问 `127.0.0.1:23333`（同机部署）
4. **API 密钥**：`.env` 已在 `.gitignore` 中，切勿将 Secret 提交到 Git
5. **群管理权限**：抽奖禁言依赖 QQ 群管理接口，机器人需要具备群管理员权限；群主、管理员和机器人账号不能被该接口禁言
6. **投票候选项上限**：QQ 单条内联键盘最多放置 25 个按钮（含提交按钮），因此最多 24 个候选项；本项目不会为超限候选项自动分页
7. **腾讯表格权限**：候选表必须允许通过分享链接查看；无需在配置中保存腾讯文档访问令牌
