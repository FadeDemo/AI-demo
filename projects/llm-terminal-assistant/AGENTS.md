# LLM Terminal Assistant Agent 规则

除仓库级规则外，以下规则适用于 `llm-terminal-assistant` 项目。

## 结构化输出请求编码

- 将 `ModelRequest.output_format` 视为提供方 API 选项。OpenAI Responses API
  兼容适配器将它映射到 `text.format`。
- 不得仅因为项目内置的编码器接受消息级 `response_format`，就把
  `ModelRequest.output_format` 加入 DeepSeek Prompt 编码器或 Token 预算输入。
  该能力不能证明 DeepSeek 托管的 Responses API 会如何把 `text.format` 映射到
  模型 Prompt。
- 在没有该托管 API 映射证据时，不得把 Prompt 编码器目前未编码 Schema
  报告为缺陷。
- 任何改变此边界的建议，都必须提供提供方的最新证据、到项目内置编码器的
  具体映射方式，以及编码结果示例。如果只能确认 Token 统计行为，仍须明确说明
  具体的 Prompt 转换方式尚未查明。
