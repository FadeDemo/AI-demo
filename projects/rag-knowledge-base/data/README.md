# 文档语料

`docs/` 是任务 1 使用的语料根目录，共 50 篇 UTF-8 Markdown 短文。每份文件对应一篇文档，后续检索实验复用这批资料。

## 来源与练习使用范围

根目录中的 `超时.md`、`日志.md`、`预算.md` 来自[文档与关键词检索课程](../../../notes/rag/retrieval-and-documents.md)的手算样本。其余 47 篇是为本项目编写的教学短文，依据下表所列仓库课程或本项目已有实现改写。

这些自编样本用于本仓库的学习、检索和评测练习，允许在这些练习中复制、修改和重新分组。所列课程链接便于核对概念出处。外部原文如需另行引用，其使用范围按原出处的许可处理。

新增短文按 Python 环境、请求处理、上下文、输出处理和工程测试分组。短文中的应用策略采用课程约定，涉及提供方行为时应结合实际选择的接口核对。

## 文件清单

| 文件                                                                            | 内容出处                                                                      |
| ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| [超时.md](docs/超时.md)                                                         | [文档与关键词检索](../../../notes/rag/retrieval-and-documents.md)             |
| [日志.md](docs/日志.md)                                                         | [文档与关键词检索](../../../notes/rag/retrieval-and-documents.md)             |
| [预算.md](docs/预算.md)                                                         | [文档与关键词检索](../../../notes/rag/retrieval-and-documents.md)             |
| [python/virtual-environment.md](docs/python/virtual-environment.md)             | [Python 虚拟环境](../../../notes/python/virtual-environments.md)              |
| [python/interpreter-path.md](docs/python/interpreter-path.md)                   | [Python 虚拟环境](../../../notes/python/virtual-environments.md)              |
| [python/uv-sync.md](docs/python/uv-sync.md)                                     | [Python 包管理](../../../notes/python/package-management.md)                  |
| [python/dependency-lock.md](docs/python/dependency-lock.md)                     | [Python 包管理](../../../notes/python/package-management.md)                  |
| [python/project-dependencies.md](docs/python/project-dependencies.md)           | [Python 包管理](../../../notes/python/package-management.md)                  |
| [python/src-layout.md](docs/python/src-layout.md)                               | [项目包结构与运行说明](../README.md)                                          |
| [python/package-init.md](docs/python/package-init.md)                           | [项目包结构与运行说明](../README.md)                                          |
| [python/absolute-import.md](docs/python/absolute-import.md)                     | [项目命令行导入方式](../src/rag_knowledge_base/cli.py)                        |
| [python/relative-path.md](docs/python/relative-path.md)                         | [文档与关键词检索](../../../notes/rag/retrieval-and-documents.md)             |
| [python/utf8-files.md](docs/python/utf8-files.md)                               | [文档与关键词检索](../../../notes/rag/retrieval-and-documents.md)             |
| [requests/message-roles.md](docs/requests/message-roles.md)                     | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [requests/request-response.md](docs/requests/request-response.md)               | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [requests/fake-client.md](docs/requests/fake-client.md)                         | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [requests/request-timeout.md](docs/requests/request-timeout.md)                 | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [requests/retry-limit.md](docs/requests/retry-limit.md)                         | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [requests/retry-backoff.md](docs/requests/retry-backoff.md)                     | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [requests/retryable-errors.md](docs/requests/retryable-errors.md)               | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [requests/authentication-error.md](docs/requests/authentication-error.md)       | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [requests/rate-limit.md](docs/requests/rate-limit.md)                           | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [requests/finish-reason.md](docs/requests/finish-reason.md)                     | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [context/token-count.md](docs/context/token-count.md)                           | [Token 与上下文](../../../notes/llm/tokens-and-context.md)                    |
| [context/context-window.md](docs/context/context-window.md)                     | [Token 与上下文](../../../notes/llm/tokens-and-context.md)                    |
| [context/output-reserve.md](docs/context/output-reserve.md)                     | [Token 与上下文](../../../notes/llm/tokens-and-context.md)                    |
| [context/request-budget.md](docs/context/request-budget.md)                     | [Token 与上下文](../../../notes/llm/tokens-and-context.md)                    |
| [context/history-growth.md](docs/context/history-growth.md)                     | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [context/history-pruning.md](docs/context/history-pruning.md)                   | [Token 与上下文](../../../notes/llm/tokens-and-context.md)                    |
| [context/sampling-temperature.md](docs/context/sampling-temperature.md)         | [生成参数与采样](../../../notes/llm/generation-parameters.md)                 |
| [context/top-p.md](docs/context/top-p.md)                                       | [生成参数与采样](../../../notes/llm/generation-parameters.md)                 |
| [output/streamed-text.md](docs/output/streamed-text.md)                         | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [output/stream-failure.md](docs/output/stream-failure.md)                       | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [output/partial-output.md](docs/output/partial-output.md)                       | [结构化输出](../../../notes/llm/structured-output.md)                         |
| [output/json-parse.md](docs/output/json-parse.md)                               | [结构化输出](../../../notes/llm/structured-output.md)                         |
| [output/schema-validation.md](docs/output/schema-validation.md)                 | [结构化输出](../../../notes/llm/structured-output.md)                         |
| [output/structured-output.md](docs/output/structured-output.md)                 | [结构化输出](../../../notes/llm/structured-output.md)                         |
| [output/tool-arguments.md](docs/output/tool-arguments.md)                       | [工具调用](../../../notes/llm/tool-calling.md)                                |
| [output/tool-permissions.md](docs/output/tool-permissions.md)                   | [工具调用](../../../notes/llm/tool-calling.md)                                |
| [output/tool-round-limit.md](docs/output/tool-round-limit.md)                   | [工具调用](../../../notes/llm/tool-calling.md)                                |
| [engineering/log-level.md](docs/engineering/log-level.md)                       | [日志基础](../../../notes/engineering/logging.md)                             |
| [engineering/request-id.md](docs/engineering/request-id.md)                     | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [engineering/timing-logs.md](docs/engineering/timing-logs.md)                   | [流式输出与可靠性](../../../notes/llm/streaming-and-reliability.md)           |
| [engineering/credential-redaction.md](docs/engineering/credential-redaction.md) | [安全、评测与可观测性](../../../notes/llm/safety-evaluation-observability.md) |
| [engineering/stdout-stderr.md](docs/engineering/stdout-stderr.md)               | [日志基础](../../../notes/engineering/logging.md)                             |
| [engineering/unit-test.md](docs/engineering/unit-test.md)                       | [基础测试](../../../notes/engineering/basic-testing.md)                       |
| [engineering/integration-test.md](docs/engineering/integration-test.md)         | [基础测试](../../../notes/engineering/basic-testing.md)                       |
| [engineering/test-fixture.md](docs/engineering/test-fixture.md)                 | [基础测试](../../../notes/engineering/basic-testing.md)                       |
| [engineering/config-environment.md](docs/engineering/config-environment.md)     | [模型调用与消息](../../../notes/llm/model-calls-and-messages.md)              |
| [engineering/prompt-injection.md](docs/engineering/prompt-injection.md)         | [安全、评测与可观测性](../../../notes/llm/safety-evaluation-observability.md) |
