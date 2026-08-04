---
title: 基础测试练习回答
type: answer
area: engineering
status: completed
created: 2026-08-04
updated: 2026-08-04
tags:
  - engineering
  - testing
  - pytest
  - answers
---

# 基础测试练习回答

本文记录[基础测试](../basic-testing.md)课程“练习与验收”中的稳定书面结论。测试代码保存在 `projects/engineering-foundations/` 中，不在此重复粘贴；测试数量、运行耗时等可能随代码变化的结果也不作为留档内容。

## 从行为到 Arrange、Act、Assert

`test_search_normalizes_query` 保护的行为是：查询词的大小写和首尾空格不同，不应改变搜索结果。它并不要求 `search_documents()` 必须调用某一种字符串处理方法。

- Arrange：`sample_documents` fixture 提供两篇与 `RAG` 匹配的文档和一篇不匹配的文档，参数化为每次测试提供一个查询词。
- Act：调用 `search_documents()`，并传入当前查询词和测试用的 `request_id`。
- Assert：检查结果的 `source` 列表等于 `["more.md", "rag.md"]`，同时验证命中内容和稳定排序，而不是只比较三次调用彼此相等。

参数化用例失败时，pytest 会在测试节点名称中标出对应的查询参数，并展示实际列表与预期列表的差异。因此可以判断是哪一种输入破坏了规则。

`test_invalid_limit_is_rejected` 保护的是另一个外部可观察行为：`limit` 小于 1 时，调用者得到消息明确的 `ValueError`，运维侧同时得到包含稳定上下文字段的 `WARNING`。测试不关心函数内部使用 `if`、辅助函数还是其他方式完成校验。

## pytest 工具的职责

| 工具            | 本课中解决的问题                                                              |
| --------------- | ----------------------------------------------------------------------------- |
| 参数化          | 让多个查询词或非法 `limit` 复用同一条行为规则，同时保留彼此独立的失败结果     |
| fixture         | 通过 `sample_documents` 统一提供有明确含义的测试前置条件                      |
| `tmp_path`      | 为每次测试提供独立的临时目录，避免固定测试文件互相污染或遗留在仓库中          |
| `pytest.raises` | 同时约束异常类型和稳定的错误消息，避免无关异常让失败路径测试错误通过          |
| `caplog`        | 捕获 `LogRecord`，检查日志级别以及 `event`、`request_id`、`reason` 等稳定字段 |

这些工具解决的问题不同。参数化负责多组输入，fixture 负责准备条件，`tmp_path` 是 pytest 提供的一种内置 fixture，`pytest.raises` 观察异常契约，`caplog` 观察日志契约。

## 当前项目的测试层次

配套项目的核心搜索逻辑接收内存中的 `Document` 列表，不连接数据库、网络或模型 API。大部分测试直接调用 `search_documents()` 并观察返回值、异常和日志，因此主要属于快速、隔离的单元测试。

任务 4 使用真实临时文件准备测试数据：测试先写入并读取 `guide.md`，再用读取结果构造 `Document`。这展示了如何用 `tmp_path` 隔离文件资源，但文件读取仍然发生在测试准备代码中，产品代码没有提供 Markdown 加载器。因此，该测试不能证明应用已经具备从路径发现、解析并加载 Markdown 文档的完整功能。若以后增加产品级文件加载模块，应再为加载模块与搜索模块的协作编写集成测试。

## Stub、Fake 与 Mock 的比较（选做）

- Stub 控制依赖的返回结果。`StubModelClient` 无论收到什么问题都返回固定答案，适合测试业务代码如何处理一个预设响应。
- Fake 提供简化但可以工作的实现。`FakeModelClient` 从内存字典查询答案，可以覆盖多个输入，又不访问真实模型服务。
- Mock 既可以配置返回值，也可以验证交互。示例中的 `Mock` 检查 `generate()` 是否收到原始问题并且只调用一次，适合调用方式本身属于契约的场景。

三者不是按“高级程度”排列。选择时应先判断测试需要控制返回结果、模拟一套轻量行为，还是验证与依赖的交互。
