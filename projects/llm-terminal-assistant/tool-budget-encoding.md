# 工具预算编码规则

本文记录 `llm-terminal-assistant` 将工具相关请求转换为本地预算输入时采用的规则。预算流程先编码完整请求，再由 Token 计数器统计编码文本；工具定义、调用参数和工具结果都属于输入预算。

## 协议映射与编码职责

`adapter/protocol_mapping.py` 集中维护项目输入类型到目标格式的映射，函数名标明目标格式：

- `to_openai_responses_input_item` 转换单个输入项，目标是 OpenAI Responses API 的输入格式。普通消息保留 `role`、`content`；工具调用转换为该 API 的 `function_call`；工具结果转换为该 API 的 `function_call_output`，两者通过 `call_id` 对应。
- Fake 客户端的预算编码复用上述输入映射，并编码工具定义。这是项目选择的 Fake 编码格式。
- `to_deepseek_messages` 转换整个请求的输入列表，目标是项目内置的 DeepSeek 官方消息编码器接受的格式。归并工具调用需要相邻项信息，因此不采用独立的单项转换。
- `deepseek_prompt_encoder.py` 负责选择 DeepSeek 编码器及推理设置，将转换后的消息交给官方编码实现生成文本；不在映射函数中手写模型特殊标记。

## DeepSeek 工具定义

DeepSeek [官方编码说明的工具调用一节](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/dba1be0a40aa45a94ad051997016db3960a90277/encoding/README.md#tool-calling-dsml-format)明确说明，工具定义通过 `system` 消息的 `tools` 字段提供。官方消息编码示例也采用这一组织方式，简化表示为：

```python
{
    "role": "system",
    "content": "You are a helpful assistant.",
    "tools": tools,
}
```

项目让 `system` 消息携带工具定义，是参考这一官方格式和示例。工具采用嵌套的 `type: "function"`、`function` 对象，参数 Schema 放在 `function.parameters`。这是官方消息编码器的输入格式；发送到 DeepSeek 托管 Responses API 时，仍由提供方适配器处理该 API 的请求格式。

项目的放置规则是：

1. `request.tools` 为空时，不附加工具定义，也不为了工具新增消息。
2. 有工具且转换后的第一条消息是 `system` 时，将定义附加到该消息，保留原有正文。
3. 有工具且第一条消息不是 `system` 时，在开头新增 `{"role": "system", "content": ""}` 并附加定义；保留原来的第一条消息。即使后面存在其他 `system` 消息，也采用这条规则。
4. 只附加一次，保留全部工具及其顺序。每个工具包含 `name`、`description`、完整的 `parameter_schema`。
5. `parameter_schema` 已是 JSON Schema 字典，直接作为 `function.parameters` 的值传入；不提前转换为 JSON 字符串，不只提取 `properties`。

由 `system` 消息承载工具定义有官方依据；选择第一条消息，以及缺少开头 `system` 时新增空正文消息，是项目在此基础上补充的策略。官方示例没有完整规定已有多条消息时应选择哪一条，或缺少 `system` 时应如何补充。

## DeepSeek 工具调用与归并

项目的 `ToolCallRequest` 映射到 DeepSeek 官方消息编码器的 assistant 消息级 `tool_calls`，每个调用保留调用 ID、工具名和参数字符串：

```json
{
  "id": "call-1",
  "type": "function",
  "function": {
    "name": "lookup_clock",
    "arguments": "{\"timezone\":\"UTC\"}"
  }
}
```

DeepSeek 托管 Responses API 文档说明，该 API 的 `function_call` 会归并到相邻的 assistant 消息。项目在这个约束下明确采用以下策略：

1. 优先归并到前一条已转换出的 assistant 消息。
2. 如果前一条不是 assistant，则检查输入中紧接着的下一项；如果它是 assistant `Message`，使用它的正文，并消费该项一次，避免重复输出。
3. 两侧都不可用时，新建正文为空的 assistant 消息，容纳该调用。
4. 连续调用可以依次追加到同一条已转换出的 assistant 消息，保留调用顺序和各自 ID。
5. 不跨过 user、system 或工具结果寻找可归并的 assistant。使用前一条时，不吞掉后面独立的 assistant 正文。

文档中的“相邻归并”是官方说明；优先方向、连续调用组织方式和没有相邻 assistant 时的补充规则是项目策略，不能据此断言托管服务器内部采取完全相同的处理。

## DeepSeek 工具结果

项目的 `ToolCallResult` 映射为 DeepSeek 官方消息编码器接受的工具消息：

```json
{
  "role": "tool",
  "tool_call_id": "call-1",
  "content": "12:00 UTC"
}
```

`tool_call_id` 保留项目结果中的 `call_id`，`content` 保留完整的 `output` 字符串。这种工具消息格式有 DeepSeek 官方编码器的说明和示例，也出现在 DeepSeek Chat Completions API 的工具调用示例中。官方编码器负责把工具结果转换为 Prompt 中的 `<tool_result>` 内容；项目不自行构造该标签。

DeepSeek 托管 Responses API 明确支持 `function_call_output`，但没有明确公布它到上述消息格式的内部转换过程。因此，项目采用官方编码器支持的工具消息作为本地预算输入，而不把它描述成已经验证的托管服务器内部映射。

## 输入边界与一致性

- 转换不修改原始请求、消息或工具定义。除上述调用归并外，保留输入项的顺序和正文，调用与结果通过各自 ID 对应。
- `Budgeter.check()` 在编码和计数前拒绝空输入列表，抛出 `ValueError`；包含空正文消息的非空列表仍然有效。`to_deepseek_messages` 对空列表返回空列表，不单独补入工具定义。
- 工具参数 Schema 属于工具定义，应参与编码。约束最终响应的结构化输出 Schema 属于另一条链路，保持 [AGENTS.md 中的编码边界](AGENTS.md#结构化输出与工具参数-schema-的编码边界)。
- DeepSeek V4 与 V4.1 共用项目消息映射，各自的官方编码器负责对应版本的 Prompt 标记差异。两者都应验证工具定义、调用与结果进入编码文本。
- 本地预算依据内置编码器及 Token 计数器计算；官方公开格式可以作为实现依据，但不能保证本地编码文本和 Token 数与托管服务完全相同。

## 官方依据

- [DeepSeek V4 官方编码说明（项目固定版本）](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/blob/7872f01b1d1fe23eabc4c98b48bffcef5a386062/encoding/README.md)：消息级工具定义、assistant 工具调用与工具结果的编码规则。
- [DeepSeek V4.1 官方编码说明（项目固定版本）](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/dba1be0a40aa45a94ad051997016db3960a90277/encoding/README.md)：对应版本的消息格式和工具编码。
- [DeepSeek Responses API 中文指南](https://api-docs.deepseek.com/zh-cn/guides/responses_api/)与[英文指南](https://api-docs.deepseek.com/guides/responses_api/)：该 API 的调用归并说明及工具结果支持。
- [DeepSeek 工具调用中文指南](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)与[英文指南](https://api-docs.deepseek.com/guides/tool_calls/)：其中 `client.chat.completions.create` 示例属于 DeepSeek Chat Completions API，不能当作 Responses API 内部转换过程的证明。
