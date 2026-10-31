# 本次任务：确认 Agent 回复的发送长度限制

## 实现方案
- 检查 Agent 模型请求的输出 token 配置。
- 检查最终 Agent 回复的发送路径，确认是否有字符截断或分段逻辑。
- 将代码层限制与 QQ 平台可能存在的限制区分说明。

## 预期效果
- 明确告知当前 Agent 消息是否存在项目代码设置的发送长度限制，以及相关 token 上限。

## 完成情况
- 已检查 `features/agent/service.py`：模型请求设置 `max_tokens=1200`。
- 已检查 `bot_client.py` 和 `presentation/reply_payload.py`：Agent 文本回复构造后由 `message.reply` 单条发送，项目代码未做字符截断或自动分段。
- 结论已向用户说明；本次仅排查，没有修改业务代码。

**状态：已完成**
