# 修复 Agent 读取 QQ 群文件附件

## 实现方案
1. 保留现有十分钟群记忆与引用索引关联，从当前消息、引用消息或明确提及的最近文件中选择附件。
2. 将 QQ 群文件 CDN `grouptalk.c2c.qq.com` 加入附件下载白名单，仅允许 HTTPS/443 和精确主机名，并继续禁止重定向。
3. 仅向图片媒体 CDN `multimedia.nt.qq.com.cn` 发送 QQBot 授权头；请求群文件 CDN 时保留事件中的附件 URL，不转发机器人凭证。
4. 保留文本文件类型筛选、大小与输入量限制，以及把文件正文作为不可信输入的现有流程。

## 预期效果
引用或刚发送的 `.log` 文件（例如 `latest.log`）来自 QQ 群文件 CDN 时，Agent 能在现有限制内读取实际内容并汇报；URL 和认证信息不会进入模型上下文或日志。非白名单主机、非 HTTPS 地址和重定向仍会被拒绝。

## 验证结果
- 覆盖群文件 CDN 下载与授权头隔离；现有测试覆盖非白名单主机拒绝和引用附件按索引关联。
- `python -X utf8 -m unittest tests.agent.test_quoted_media tests.agent.test_file_input tests.agent.test_memory`：15 项通过。
- `python -X utf8 -m py_compile bot_client.py external_tools/qq/botpy_compat.py external_tools/storage/group_memory.py features/agent/file_input/__init__.py features/agent/vision/image_input.py tests/agent/test_quoted_media.py tests/agent/test_file_input.py`：通过。
- `git diff --check`：通过。

状态：已完成。
