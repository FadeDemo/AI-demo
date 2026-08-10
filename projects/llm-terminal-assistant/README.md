# LLM Terminal Assistant

该项目配套 [LLM 使用基础](../../notes/llm/index.md)专题，当前实现集中验证[模型调用与消息](../../notes/llm/model-calls-and-messages.md)课程中的适配层边界和两轮对话。任务 1 的书面调用链保存在[模型调用与消息练习回答](../../notes/llm/answers/model-calls-and-messages.md)中。

## 当前能力

- 使用项目自己的 `Message`、`ModelRequest`、`ModelResponse` 和 `ModelClient`，业务对话逻辑不依赖 SDK 原始响应对象。
- 通过 `client_factory` 按配置选择 `FakeClient` 或 `OpenAIClient`；fake 路径不导入 OpenAI SDK，不访问网络，也不产生模型费用。
- 完成两轮终端对话，第二轮依次发送 `system`、第一轮 `user`、第一轮 `assistant` 和第二轮 `user`。
- 每轮发送前只记录消息数量、有序角色列表和逐条正文字符数，不把消息正文写入日志。
- 将 OpenAI Responses API 的正文、结束状态、usage 和工具请求转换为项目自己的 `ModelResponse`。

当前课程阶段不执行工具请求，也没有实现无限轮会话、历史裁剪、流式响应或重试。连接失败和超时等 SDK 异常的转换边界位于 `OpenAIClient.send()`，捕获逻辑尚待后续可靠性课程实现。

## 项目结构

```text
src/llm_terminal_assistant/
├── adapter/
│   ├── fake_client.py
│   └── openai_client.py
├── cli.py
├── client.py
├── client_factory.py
├── config.py
├── message.py
└── model.py
```

- `cli.py`：终端输入、两轮消息组装、安全元数据日志和结果展示。
- `client.py`：`ModelClient` 协议。
- `client_factory.py`：根据 provider 延迟导入并创建适配器。
- `config.py`：加载项目根目录 `.env` 和进程环境变量。
- `message.py`、`model.py`：服务商无关的消息、请求、响应、usage 和工具请求结构。
- `adapter/`：fake 与 OpenAI 的具体客户端实现。

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
