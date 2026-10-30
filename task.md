# 核查是否由本项目主动删除成员提及

## 实现方案
1. 检索项目内正文修改、提及清洗、原始载荷读取和事件去重逻辑。
2. 检查已安装 BotPy 从网关事件到 GroupMessage 的解析源码，使用合成载荷核验是否原地修改输入。
3. 区分正文删除、昵称字段丢失及重复事件被忽略，给出代码位置与验证结论。

## 预期效果
明确原始调试日志缺少 mentions 是否由本项目或 SDK 主动移除造成；本次先排查，不改事件处理策略。

状态：进行中。

## 完成结果
- 检索项目主动删除提及的代码：features/commands/text.py:8 确实用正则删除所有原生提及，但只生成命令匹配用的新字符串；未修改 message.content，也未改原始 payload。
- bot_client.py:475 直接从 message.content 构造 Agent 问题，未使用上述清洗结果。
- 检查本机 BotPy 网关解码、GROUP_AT_MESSAGE_CREATE 解析器、BaseMessage 初始化及项目兼容层，未发现对输入 content 或 mentions 的删除；调试日志位于 GroupMessage 初始化后、业务路由和去重前。
- 使用同一合成载荷分别调用真实 GROUP_AT_MESSAGE_CREATE 和 GROUP_MESSAGE_CREATE 解析器，断言原始事件深比较不变、正文保留、member_openid 保留、命令标准化后正文不变，全部通过。
- SDK 的 GroupMessage._User 仅保留 member_openid，确实会丢弃 username/id 等其他字段，但不修改原始 mentions，因此不能导致 raw_mentions_present=false。
- 确认另一个信息遗漏点：bot_client.py:131 对重复消息直接返回；未合并后到事件的正文或提及、未补全历史。此问题在原始调试日志之后，不能解释原始字段缺失。
- 结论：本机所查代码不会造成此前原始调试日志中的正文/mentions 缺失；命令清洗、SDK 昵称丢失、重复事件不合并是三个不同问题。部署端额外改动仍需与本机版本一致才能排除。
- 本次仅排查和运行合成验证，未修改业务代码或重启机器人。

状态：已完成。
