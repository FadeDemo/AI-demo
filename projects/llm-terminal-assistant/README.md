# LLM Terminal Assistant

该项目配套 [LLM 使用基础](../../notes/llm/index.md)专题，当前实现验证[模型调用与消息](../../notes/llm/model-calls-and-messages.md)课程中的适配层边界和多轮对话，并为 [Token 与上下文窗口](../../notes/llm/tokens-and-context.md)课程提供固定样本、Token 计数入口、请求预算和历史裁剪实现。相关书面记录保存在 [LLM 使用基础练习回答](../../notes/llm/answers/index.md)中。

## 当前能力

- 使用项目自己的 `Message`、`ModelRequest`、`ModelResponse` 和 `ModelClient`，业务对话逻辑不依赖 SDK 原始响应对象。
- 通过 `client_factory` 按配置选择 `FakeClient` 或 `OpenAIClient`；`FakeClient` 不导入 OpenAI SDK、不调用远程生成服务，也不产生模型费用，预算计数所需资源由 `MODEL` 独立决定。
- 支持持续进行终端对话，并把成功响应后的 `user` 和 `assistant` 消息保存为完整问答轮次。
- 每轮发送前只记录消息数量、有序角色列表和逐条正文字符数，不把消息正文写入日志。
- 每次生成调用前执行请求级 Token 预算检查；上下文窗口或最大输入超限时，按完整问答轮次从旧到新裁剪历史，直到请求通过或达到强制保留边界。
- 将 OpenAI Responses API 的正文、结束状态、usage 和工具请求转换为项目自己的 `ModelResponse`。
- 使用固定 revision 的 DeepSeek-V4-Flash-0731 tokenizer 统计中文、英文、JSON 和 Python 代码样本的原始文本 Token 数。
- 提供显式的 `fake-model` 合成模型，使 fake 客户端可以在不安装真实 tokenizer、不读取模型缓存和不访问网络的情况下运行。

当前课程阶段不执行工具请求，也没有实现旧历史摘要、流式响应或重试。连接失败和超时等 SDK 异常的转换边界位于 `OpenAIClient.send()`，捕获逻辑尚待后续可靠性课程实现。

## 项目结构

```text
src/llm_terminal_assistant/
├── adapter/
│   ├── deepseek_prompt_encoder.py
│   ├── fake_client.py
│   ├── fake_model.py
│   ├── huggingface_tokenizer.py
│   └── openai_client.py
├── budgeter.py
├── budgeter_factory.py
├── cli.py
├── client.py
├── client_factory.py
├── config.py
├── conversation.py
├── message.py
├── model.py
├── token_count_cli.py
└── token_counter.py
tests/
├── test_budgeter.py
├── test_budgeter_factory.py
├── test_conversation.py
└── test_openai_client.py
```

- `budgeter.py`、`budgeter_factory.py`：预算公式、稳定拒绝原因，以及模型对应的请求编码器和计数器装配。
- `cli.py`：终端输入、多轮发送流程、安全元数据日志和结果展示。
- `client.py`：`ModelClient` 协议。
- `client_factory.py`：根据 provider 延迟导入并创建适配器。
- `config.py`：加载项目根目录 `.env` 和进程环境变量。
- `conversation.py`：完整问答轮次、候选请求组装和历史裁剪策略。
- `message.py`、`model.py`：服务商无关的消息、请求、响应、usage 和工具请求结构。
- `token_counter.py`：Token 计数器协议。
- `token_count_cli.py`：读取四类固定样本并输出字符数、Token 数和计数环境元数据。
- `adapter/`：fake、OpenAI、DeepSeek 请求编码和 Hugging Face tokenizer 的具体适配实现。
- `tests/`：完全离线的预算边界、生成调用拦截、fake-model 和 OpenAI 请求映射测试。

## 安装

项目需要 Python 3.13 和 uv。运行完全离线的 fake 客户端或默认自动化测试时只需执行：

```shell
cd projects/llm-terminal-assistant
uv sync
```

需要调用 OpenAI 或兼容 Responses API 的远程服务时，安装可选依赖：

```shell
uv sync --extra openai
```

需要运行 Token 计数入口时，安装 Hugging Face Transformers 计数依赖：

```shell
uv sync --extra token-counting
```

## 配置

程序从项目根目录的 `.env` 或当前进程环境读取以下变量：

| 变量       | 含义                                      |
| ---------- | ----------------------------------------- |
| `PROVIDER` | 客户端类型：`faked` 或 `openai`           |
| `API_KEY`  | 远程模型服务凭据；fake 模式不会使用       |
| `BASE_URL` | OpenAI Responses API 或兼容服务的基础 URL |
| `MODEL`    | 请求使用的模型标识或显式的 `fake-model`   |

本地 `.env` 不应提交。示例值必须使用占位符：

```dotenv
PROVIDER=openai
API_KEY=<your-api-key>
BASE_URL=https://api.example.com/v1
MODEL=<model-id>
```

进程环境变量优先于 `.env` 中的同名值。不要把真实凭据写入源码、README、命令历史或日志。

历史裁剪使用应用配置 `min_reserved_recent_turns` 声明至少保留的最近完整轮次数，当前默认值为 1。该值属于应用策略，不发送给模型服务，也不通过环境变量覆盖。

## 运行

### 完全离线的 Fake 客户端和模型

使用 `faked` provider 和显式的 `fake-model`，可以离线验证预算拦截、多轮消息顺序和历史裁剪后的发送路径，不需要 API Key、真实 tokenizer 或模型缓存：

```shell
PROVIDER=faked MODEL=fake-model uv run llm-terminal-assistant
```

`fake-model` 是公开规则明确的合成模型，不模拟任何真实模型的 Token 数。它先把消息和 reasoning effort 编码为规范 JSON，再把编码结果的每个 Unicode code point 计作一个合成 Token；其上下文窗口为 32768，最大输入为 16384，最大输出为 8192。该规则只用于完全离线的运行路径。

输入前两轮问题后，程序会返回固定响应，并分别记录类似以下的安全元数据；之后可以继续输入更多轮次，直到输入 `exit`：

```text
message_count=2 roles=['system', 'user'] content_lengths=[28, 14]
message_count=4 roles=['system', 'user', 'assistant', 'user'] content_lengths=[28, 14, 23, 15]
```

长度随实际输入变化；日志不应出现消息正文。

如果只让生成客户端使用 fake 响应，同时仍按 DeepSeek-V4-Flash-0731 的真实消息格式和 tokenizer 检查预算，则执行：

```shell
PROVIDER=faked MODEL=deepseek-v4-flash \
  uv run --extra token-counting llm-terminal-assistant
```

这条路径不会调用远程模型生成服务，但首次准备 tokenizer 时仍可能访问 Hugging Face Hub。准备缓存后可以设置 `HF_HUB_OFFLINE=1` 强制只读取本地文件。fake 客户端和模型计数契约是两个独立选择；程序不会因为 provider 是 `faked` 而把真实模型的计数规则静默替换为合成规则。

### 请求预算

预算器先用目标模型的消息编码器生成完整输入，再把编码结果交给 Token 计数器。剩余空间按以下公式计算：

```text
remaining_tokens = context_window_tokens
                   - estimated_input_tokens
                   - reserved_output_tokens
                   - safety_margin_tokens
```

所有单项限制满足且 `remaining_tokens` 大于或等于 0 时才调用生成客户端。拒绝请求时不调用客户端，并提供稳定原因：`negative_limit`、`max_input_exceeded`、`max_output_exceeded` 或 `context_window_exceeded`。

不同提供方和接口使用不同的输出限制参数。本项目的 OpenAI 适配器调用 OpenAI Responses API 时，把单次请求的 `reserved_output_tokens` 映射为该接口的 `max_output_tokens`。应用预算策略使用的 `safety_margin_tokens` 不发送给模型服务。

### 历史裁剪

每轮请求先使用完整活跃历史执行预算检查。只有 `context_window_exceeded` 或 `max_input_exceeded` 才触发历史裁剪；负数限制和输出上限超限不能通过减少输入解决，程序会直接拒绝请求。

裁剪策略遵循以下规则：

- 持续生效的 `system` 消息和本轮 `user` 消息始终保留。
- 已完成历史以一组相邻的 `user` 与 `assistant` 消息作为一个完整裁剪单位，不单独删除其中一条消息。
- 从最早的完整轮次开始逐轮删除，每次删除后重新执行请求级预算检查。
- 至少保留最近 1 个完整轮次；如果当前历史不足 1 轮，则保留全部现有历史。
- 预算内历史保持不变，裁剪函数也不修改调用方传入的原历史列表。
- 达到最少保留轮数后仍无法通过预算检查时，保留原预算拒绝原因并且不调用模型生成客户端。

当前实现不生成旧历史摘要。后续如果增加摘要，须另行声明摘要的来源追踪和失败行为。

### OpenAI 客户端

配置 `PROVIDER=openai`、凭据、基础 URL 和模型后执行：

```shell
uv run --extra openai llm-terminal-assistant
```

这条路径会访问远程模型服务，可能产生费用并占用速率限额。只有手动集成验收才应使用真实凭据；默认验证使用 fake。

### Token 计数

计数入口使用项目模型标识 `deepseek-v4-flash` 查找模型配置，再通过 Hugging Face Transformers 的 `AutoTokenizer.from_pretrained()` 加载 DeepSeek 官方 `deepseek-ai/DeepSeek-V4-Flash-0731` 仓库中固定 revision 的 tokenizer。它读取 `samples/token-counting/` 下的中文、英文、JSON 和 Python 文件原始文本，输出样本路径、原文、Python `len()` 字符数、Token 数、模型标识、仓库、revision 及计数工具版本。

在项目目录执行：

```shell
MODEL=deepseek-v4-flash uv run --extra token-counting token-count
```

首次运行时，Hugging Face Transformers 可能访问 Hugging Face Hub 并把 tokenizer 文件下载到本地缓存；这一步不调用远程模型推理 API，也不产生模型推理费用。`token-count` 是使用真实 tokenizer 的计数入口，不作为项目后续默认自动化测试的一部分，因为全新测试环境不一定已有 tokenizer 缓存，也不应为了运行测试而访问网络。后续预算器测试改用不读取 Hugging Face 缓存的确定性 fake 计数器。默认缓存目录为 `~/.cache/huggingface/hub`，可通过 Hugging Face Hub 的 `HF_HOME` 或 `HF_HUB_CACHE` 环境变量修改。缓存准备完成后，可通过 Hugging Face Hub 的 `HF_HUB_OFFLINE=1` 环境变量强制只使用本地缓存：

```shell
HF_HUB_OFFLINE=1 MODEL=deepseek-v4-flash \
  uv run --extra token-counting token-count
```

离线命令在指定 revision 的 tokenizer 文件尚未缓存时会失败。Hugging Face Hub 的[缓存说明](https://huggingface.co/docs/huggingface_hub/main/guides/manage-cache)和[环境变量参考](https://huggingface.co/docs/huggingface_hub/main/package_reference/environment_variables)描述了缓存位置与离线开关。本次样本计数结果和观察结论记录在 [Token 与上下文窗口练习回答](../../notes/llm/answers/tokens-and-context.md)中。

## 验证

默认自动化测试完全离线，使用确定性的 fake Token 计数器和记录调用次数的 fake 客户端，不加载 Hugging Face tokenizer、访问网络、要求 API Key 或产生模型费用：

```shell
uv run python -m unittest discover -s tests -v
```

格式化和 Lint：

```shell
uv run ruff format --check src tests
uv run ruff check src tests
```

离线手动验收：

```shell
PROVIDER=faked MODEL=fake-model uv run llm-terminal-assistant
```

依次输入至少两轮不同问题，确认：

1. 第一轮日志的 `message_count` 为 2，角色顺序为 `system`、`user`。
2. 第二轮日志的 `message_count` 为 4，角色顺序为 `system`、`user`、`assistant`、`user`。
3. 每轮 `content_lengths` 的项目数与角色数相同。
4. 日志不包含 system、user 或 assistant 消息正文。
5. 每轮都显示 fake 响应，可以继续输入后续问题，运行期间不访问网络。

自动化测试使用六个固定的完整问答轮次验证：预算内历史保持不变；上下文窗口或最大输入超限时删除最早完整轮次；裁剪后保留 `system`、本轮 `user` 和声明的最近轮次；强制内容仍超限、输出上限超限、负数限制或裁剪策略无效时不调用 fake 模型生成客户端。测试还覆盖零剩余空间的允许路径、完整消息编码、完全离线的 `fake-model` 路径，以及 OpenAI Responses API 输出上限映射。上述终端交互流程保留为手动验收方式。
