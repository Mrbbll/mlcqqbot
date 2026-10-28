# 将 Agent 系统提示词从 .env 移入 config.py

## 实现方案
1. 将人格提示词和工具规则保留为 `config.py` 中两个独立的多行常量。
2. Agent 继续在请求时拼接两段提示词，并按权限追加动态服务器上下文。
3. 从当前 `.env` 中仅移除 `AGENT_PERSONALITY_PROMPT` 和 `AGENT_TOOL_PROMPT` 两项，保留其他环境配置。
4. 将缺失配置回复恢复为只说明 API 配置项。

## 预期效果
提示词不再经过 `.env` 的多行格式解析；人格和工具规则仍可分别在 `config.py` 中维护并组合。

## 完成结果
- 人格提示词与工具规则现保存在 `config.py` 的独立多行常量中，`service.py` 继续在运行时拼接。
- 从当前 `.env` 中仅删除两项提示词变量，其他环境配置保留。
- 缺失配置回复现在只提示设置 Agent API 地址、密钥和模型。
- `python -m py_compile config.py features/agent/service.py`：通过；导入配置确认两段提示词非空。
- 确认 `.env` 中已无这两项变量；`git diff --check`：通过。

状态：已完成。
