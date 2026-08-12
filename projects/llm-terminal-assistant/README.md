# LLM Terminal Assistant

该项目配套 [LLM 使用基础](../../notes/llm/index.md)专题，当前实现集中验证[模型调用与消息](../../notes/llm/model-calls-and-messages.md)课程中的适配层边界和两轮对话，并为 [Token 与上下文窗口](../../notes/llm/tokens-and-context.md)课程提供固定样本和 Token 计数入口。相关书面记录保存在 [LLM 使用基础练习回答](../../notes/llm/answers/index.md)中。

## 当前能力

- 使用项目自己的 `Message`、`ModelRequest`、`ModelResponse` 和 `ModelClient`，业务对话逻辑不依赖 SDK 原始响应对象。
- 通过 `client_factory` 按配置选择 `FakeClient` 或 `OpenAIClient`；fake 路径不导入 OpenAI SDK，不访问网络，也不产生模型费用。
- 完成两轮终端对话，第二轮依次发送 `system`、第一轮 `user`、第一轮 `assistant` 和第二轮 `user`。
- 每轮发送前只记录消息数量、有序角色列表和逐条正文字符数，不把消息正文写入日志。
- 将 OpenAI Responses API 的正文、结束状态、usage 和工具请求转换为项目自己的 `ModelResponse`。
- 使用固定 revision 的 DeepSeek-V4-Flash-0731 tokenizer 统计中文、英文、JSON 和 Python 代码样本的原始文本 Token 数。

当前课程阶段不执行工具请求，也没有实现无限轮会话、历史裁剪、流式响应或重试。连接失败和超时等 SDK 异常的转换边界位于 `OpenAIClient.send()`，捕获逻辑尚待后续可靠性课程实现。

## 项目结构

```text
src/llm_terminal_assistant/
├── adapter/
│   ├── fake_client.py
│   ├── huggingface_tokenizer.py
│   └── openai_client.py
├── cli.py
├── client.py
├── client_factory.py
├── config.py
├── message.py
├── model.py
├── token_count_cli.py
└── token_counter.py
```

- `cli.py`：终端输入、两轮消息组装、安全元数据日志和结果展示。
- `client.py`：`ModelClient` 协议。
- `client_factory.py`：根据 provider 延迟导入并创建适配器。
- `config.py`：加载项目根目录 `.env` 和进程环境变量。
- `message.py`、`model.py`：服务商无关的消息、请求、响应、usage 和工具请求结构。
- `token_counter.py`：Token 计数器协议。
- `token_count_cli.py`：读取四类固定样本并输出字符数、Token 数和计数环境元数据。
- `adapter/`：fake、OpenAI 和 Hugging Face tokenizer 的具体适配实现。

## 安装

项目需要 Python 3.13 和 uv。仅运行 fake 客户端时执行：

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
| `MODEL`    | 请求使用的模型标识                        |

本地 `.env` 不应提交。示例值必须使用占位符：

```dotenv
PROVIDER=openai
API_KEY=<your-api-key>
BASE_URL=https://api.example.com/v1
MODEL=<model-id>
```

进程环境变量优先于 `.env` 中的同名值。不要把真实凭据写入源码、README、命令历史或日志。

## 运行

### Fake 客户端

fake 模式适合离线验证消息顺序，不需要 API Key：

```shell
PROVIDER=faked uv run llm-terminal-assistant
```

输入两轮问题后，程序会返回固定响应，并分别记录类似以下的安全元数据：

```text
message_count=2 roles=['system', 'user'] content_lengths=[28, 14]
message_count=4 roles=['system', 'user', 'assistant', 'user'] content_lengths=[28, 14, 23, 15]
```

长度随实际输入变化；日志不应出现消息正文。

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

格式化和 Lint：

```shell
uv run ruff format --check src
uv run ruff check src
```

离线手动验收：

```shell
PROVIDER=faked uv run llm-terminal-assistant
```

依次输入两轮不同问题，确认：

1. 第一轮日志的 `message_count` 为 2，角色顺序为 `system`、`user`。
2. 第二轮日志的 `message_count` 为 4，角色顺序为 `system`、`user`、`assistant`、`user`。
3. 每轮 `content_lengths` 的项目数与角色数相同。
4. 日志不包含 system、user 或 assistant 消息正文。
5. 两轮都显示 fake 响应，运行期间不访问网络。

项目目前没有自动化测试套件；上述 fake 流程是当前阶段的手动验收方式，不能将其描述为自动化测试。
