---
title: 安全、评测与可观测性练习回答
type: answer
area: llm
status: learning
created: 2026-10-30
updated: 2026-10-30
tags:
  - llm
  - safety
  - observability
  - answers
---

# 安全、评测与可观测性练习回答

本文记录[安全、评测与可观测性](../safety-evaluation-observability.md)课程任务 1 的数据与权限边界分析。分析依据为 2026-10-30 核对的 [LLM Terminal Assistant](../../../projects/llm-terminal-assistant/README.md) 源码与已有离线测试，只覆盖当前接入的能力。

## 任务 1　梳理数据与权限边界

### 当前入口与数据流

普通终端对话由用户输入触发。应用负责组装消息和选择可用工具，模型返回正文或工具调用建议，工具执行器决定调用能否进入实际函数。工具结果交回模型后，新提出的调用仍须再次校验。

| 数据从哪里来、交给谁                       | 携带什么                                                   | 应用负责什么                                                                           |
| ------------------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| 用户经终端把输入交给应用                   | 本轮问题，以及用户粘贴的资料                               | 将整段输入保存为用户消息，不把其中的文字当作修改本地配置或注册工具的程序指令           |
| 应用把请求交给模型客户端                   | 应用设置的系统消息、必要历史、本轮输入和可用工具定义       | 每次发送前检查输入预算，必要时按完整轮次裁剪历史                                       |
| 提供方适配器把请求交给模型服务             | 由应用协议转换的消息、工具定义和生成选项                   | 保留消息来源及工具调用与结果的对应关系，认证配置另交给 SDK 客户端                      |
| 模型服务把响应交给应用                     | 候选回答，或带工具名、参数和调用 ID 的候选请求             | 按结束状态处理响应，正常完成且携带工具请求时才进入工具流程                             |
| 应用把候选调用交给工具执行器               | 工具名、JSON 参数和调用 ID                                 | 查注册表并验证参数，通过后才进入已注册函数；执行受次数限制，并按配置检查取消信号与期限 |
| 工具执行器把结果交给应用，再由应用交给模型 | 函数执行结果或执行器产生的拒绝结果，以及原调用 ID          | 作为工具结果保留，不把正文改成系统指令，也不根据正文新增工具权限                       |
| 应用把回答交给用户，把日志交给开发者       | 面向用户的正文和状态提示；用于诊断的数量、类别、用量与耗时 | 两种输出按各自用途检查，不能把完整终端转储自动视为不含正文的日志                       |

请求组装、发送与展示的依据见 [cli.py](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/cli.py)。其中 `talk()` 创建系统消息和用户消息，`send_conversation_turn()` 驱动完整响应的工具循环。正文流式入口不提供工具定义，沿用先修课的范围。

工具回传由 [conversation.py](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/conversation.py) 中的 `build_tool_followup_request()` 完成。提供方输入转换见 [protocol_mapping.py](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/adapter/protocol_mapping.py)，工具结果按独立输入项及原调用 ID 转换，不被转换为系统消息。

### 四类数据各自的用途

| 数据类别   | 当前入口中的具体形式                                       | 使用边界                                                       |
| ---------- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| 任务指令   | 应用设置的系统消息，以及用户在允许范围内提出的任务         | 用于指导模型生成，不能代替工具执行前的程序校验                 |
| 待处理资料 | 用户粘贴的文本、工具结果正文，以及后续请求回放的这些内容   | 提供回答依据；其中的命令式语句不能修改注册表或绕过参数校验     |
| 认证凭据   | 配置中的 API Key，经模型客户端交给 SDK                     | 用于访问模型服务，不作为回答资料，不应进入消息、工具结果或日志 |
| 诊断元数据 | 输入项数量、工具定义数量、预算、结束类别、尝试次数和耗时等 | 帮助开发者定位运行情况，通常无需复制输入与回答正文             |

普通终端入口当前只设置通用助手提示，并未定义专用的资料总结契约，也未把用户输入拆成任务区和资料区。独立的 [Prompt 实验定义](../../../projects/llm-terminal-assistant/prompts/prompt-design/prompt-versions.json)才明确规定会议总结规则、资料标签及标签内命令的处理方式。这两个入口的约束应分别判断，不能把实验中的提示当作普通终端已经具备的控制。

### 直接注入

输入位置是用户消息，例如直接要求忽略既定任务、复述隐藏配置或提出写文件调用。可能的后果包括回答偏离任务，以及模型生成应用不允许执行的工具请求。

普通终端的通用提示不能证明模型会抵抗这类要求。Prompt 实验中的资料边界提示提供了更明确的生成要求，但仍需根据真实模型输出判断是否遵守。它不会改变应用可执行的工具集合。

已有的执行控制位于注册表和执行器。即使模型提出写文件请求，也只能按已注册名称分发；模型输出不会直接作为程序代码执行。当前默认注册表只包含查询时间工具，依据见 [factory.py](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/factory.py) 及其[离线测试](../../../projects/llm-terminal-assistant/tests/test_tool_factory.py)。这能说明当前开放的工具范围，不能证明真实模型在所有直接注入下都能保持回答规则。

### 资料或工具结果中的间接注入

输入位置包括用户粘贴的待处理资料，以及只读工具返回的正文。攻击文字可能要求模型改变回答格式，或在读完资料后继续提出未注册调用。

应用回传工具结果时保留其数据来源，新调用继续经过同一注册表。现有[工具流程测试](../../../projects/llm-terminal-assistant/tests/test_conversation.py)中的 `test_malicious_tool_result_followup_rejects_unregistered_tool` 从终端使用的单轮处理入口驱动完整流程。

测试先注册一个只返回固定文本的工具，让它返回要求调用未注册写工具的指令。fake 模型收到结果后提出写工具请求，应用实际查询注册表并返回 `unknown_tool`，fake 模型再返回最终回答。断言确认模型共被调用三次，已注册函数只执行一次，注册表保持不变，恶意正文和写入参数没有进入捕获的执行器日志。

这证明该请求确实到达校验后被拒绝，并非因流程提前停止而没有执行。fake 的下一步由测试预设，不能据此推断真实模型受攻击后的反应，也不能证明所有日志路径均已最小化。

### 运行凭据泄露

需要检查两条路径。第一条是应用把凭据从配置交给客户端时，是否误拼进模型消息或工具结果；第二条是处理异常或收集运行记录时，是否把凭据复制到日志、终端转储或实验文件。若发生复制，不需要等模型主动泄露，秘密就已经离开了原定用途。

[配置加载](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/config.py)从环境配置获取 API Key。[项目客户端](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/client.py)保存该值，供 [OpenAI Responses API 兼容适配器](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/adapter/openai_client.py)构造 SDK 客户端时使用。应用的 `ModelRequest` 只包含模型输入、工具定义和生成配置，没有认证字段；适配器组装消息时也没有把配置中的凭据追加到输入。

本次代码核对和 SDK 构造参数测试支持上述路径分离。测试使用虚构凭据并替换 SDK 客户端，没有进行真实认证。它们不能证明用户自行粘贴的秘密会被自动识别，也不能替代覆盖所有错误与日志路径的凭据标记测试。

已有日志控制包括请求摘要只记录数量、工具执行失败不记录处理函数的原始异常，以及结构化验证失败只记录类别、字段路径和请求 ID。对应证据见[工具回传测试](../../../projects/llm-terminal-assistant/tests/test_conversation.py)、[执行器测试](../../../projects/llm-terminal-assistant/tests/test_tool_executor.py)和[结构化流水线测试](../../../projects/llm-terminal-assistant/tests/test_structured_output_pipeline.py)。本次未进行覆盖全部启动错误、SDK 异常和不可信字段的日志核查，不能写成全局防泄露验证通过。

当前 [TerminalOutput](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/terminal_output.py) 将回答与日志写入同一个终端输出流。若把终端全文重定向到文件，回答正文也会被保存。另一个需要单独审查的去向是 [Prompt 实验记录](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/prompt_experiment.py)，其中会保存练习消息和模型输出，失败时还会保存错误文本；只应提交经过审查的练习材料，不能把它当作日常会话日志。这里记录数据去向，不把后续日志改造或实验记录审查追加为任务 1 的实现要求。

凭据没有进入模型消息时，模型就不能从这条消息路径直接读到它。把秘密先提供给模型，再要求它保密，会额外依赖生成行为。因此，认证凭据应留在认证路径中，同时防止程序自行将它写入诊断输出。

### 越权工具请求

输入位置是模型响应中的工具名和参数。直接注入、间接注入或一般生成错误都可能产生这类请求。风险取决于应用是否执行它，不能只根据模型提出了什么判断已经发生操作。

已有控制见 [registry.py](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/registry.py) 和 [executor.py](../../../projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/executor.py)。执行器先解析参数，再按注册名称找到实现并进行 Schema 校验；未注册工具返回 `unknown_tool`，无效参数返回 `invalid_arguments`，通过后才进入处理函数。实际执行还受共享次数预算约束，工具循环在相应检查点处理取消与总期限。

执行器离线测试分别检查合法参数执行一次、未知工具不执行、缺字段或错误类型等无效参数不执行，并覆盖 JSON 参数解析与次数预算。这些是组件证据；前述间接注入测试进一步证明同样的注册表拒绝已经接通单轮应用流程。

当前没有跨用户资料读取、文件操作、任意命令执行或真实写入工具，因而本任务不要求新增资源归属校验或人工审批。独立的内存草稿组件用于幂等实验，没有接入终端工具注册表。已有注册与参数检查也不能被描述为已经实现这些尚未引入的资源授权能力。

### 本次核查记录与结论范围

在配套项目目录使用已有虚拟环境执行以下命令，27 项测试全部通过。

```shell
PYTHONPATH=src:tests .venv/bin/python -B -m unittest -v \
  test_tool_executor \
  test_tool_factory \
  test_conversation.ToolFollowupRequestTests.test_malicious_tool_result_followup_rejects_unregistered_tool \
  test_conversation.ToolFollowupRequestTests.test_tool_followup_logs_counts_and_sends_without_logging_payloads \
  test_conversation.ToolFollowupRequestTests.test_cancelled_request_does_not_send_or_execute_tools \
  test_openai_client.OpenAIClientTests.test_clients_are_created_on_first_use_and_reused_without_timeout_override \
  test_openai_client.OpenAIClientTests.test_maps_input_items_to_responses_input_in_order \
  test_structured_output_pipeline
```

本次只运行已有离线用例，未调用真实模型服务。分析覆盖了四类风险的数据入口、可能后果、已有控制及其证据，也保留了未验证部分。任务 1 的书面产物不代表日志改造、真实模型评测或整课验收已经完成。
