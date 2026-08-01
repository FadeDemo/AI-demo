---
title: 基础测试
type: concept
area: engineering
status: learning
created: 2026-08-01
updated: 2026-08-01
tags:
  - engineering
  - testing
  - pytest
  - python
---

# 基础测试

自动化测试用可执行的例子描述程序应该怎样工作。它不能证明软件没有任何缺陷，但可以快速发现已经被覆盖的行为何时发生变化。好的入门测试不追求数量或覆盖率数字，而是优先保护重要行为、边界条件和已知失败模式。

本课程使用 pytest 演示。测试思想同样适用于其他语言和框架。

## 1. 从行为开始，而不是从函数开始

先写清楚需求：

> 给定三篇文档，当用户搜索 `RAG` 时，返回标题或正文包含该词的文档，并且不区分大小写。

它比“测试 `search_documents()` 函数”更有方向，因为它说明了输入、可观察结果和重要规则。一个基础测试通常使用 Arrange、Act、Assert 三段：

```python
def test_search_is_case_insensitive():
    # Arrange
    documents = [Document(title="RAG Guide", content="...", source="guide.md")]

    # Act
    results = search_documents(documents, "rag", request_id="test-request")

    # Assert
    assert [result.document.title for result in results] == ["RAG Guide"]
```

注释不是固定要求。当测试足够短时，空行就能表达三个阶段。测试名称应说明行为和条件，而不是只写 `test_search_1`。

## 2. 测试哪些情况

每个行为至少考虑三类输入：

- 正常路径：典型输入得到预期结果。
- 边界条件：空列表、空字符串、零、最大限制、重复值、Unicode 或临界时间。
- 失败路径：无效输入、文件损坏、超时或外部服务错误产生明确异常或降级结果。

不要为每一行实现机械地写一个测试。优先覆盖“如果坏了会影响用户或难以定位”的行为。文档搜索的首批测试可以是：

| 场景         | 预期行为                                 |
| ------------ | ---------------------------------------- |
| 标题命中     | 返回对应文档                             |
| 正文命中     | 返回对应文档                             |
| 大小写不同   | 仍然命中                                 |
| 没有命中     | 返回空列表，而不是抛出无关异常           |
| 空查询       | 抛出 `ValueError` 并记录受控的 `WARNING` |
| `limit` 为 0 | 明确拒绝，而不是悄悄返回空列表           |

## 3. 单元、集成与端到端测试

![不同测试层次在速度、隔离性和真实度之间的取舍](assets/testing-levels.svg)

| 层次       | 验证范围                          | 优点                   | 局限                     |
| ---------- | --------------------------------- | ---------------------- | ------------------------ |
| 单元测试   | 一个函数、类或小模块              | 快、失败位置清晰       | 不能证明组件连接正确     |
| 集成测试   | 数据库、文件系统、HTTP 客户端组合 | 更接近真实边界         | 较慢，环境准备更复杂     |
| 端到端测试 | 从外部入口到最终结果的完整流程    | 验证用户真正经过的链路 | 慢，失败原因通常更难定位 |

测试组合通常是大量快速单元测试、适量集成测试和少量关键端到端测试。这里的“测试金字塔”是取舍提示，不是固定比例。若系统主要风险来自数据库查询或模型 API 契约，就应投入足够的集成与契约测试。

RAG 还需要评测检索与生成质量。基础测试适合验证解析函数、API schema、拒答规则和已知回归；Recall@K、答案忠实度等质量指标需要固定数据集和评测流程，不能用几个普通单元测试代替。

## 4. pytest 的发现与断言

pytest 默认发现 `test_*.py` 或 `*_test.py` 文件中的 `test_*` 函数。配套项目从自己的根目录运行：

```shell
cd projects/engineering-foundations
uv sync
uv run pytest
```

只运行一个文件、一个测试或名称匹配的测试：

```shell
uv run pytest tests/test_search.py
uv run pytest tests/test_search.py::test_empty_query_is_rejected
uv run pytest -k "empty_query"
```

pytest 使用普通 `assert`，失败时会展示实际值与预期值：

```python
assert result.title == "RAG Guide"
assert len(results) == 2
assert {result.source for result in results} == {"a.md", "b.md"}
```

只有顺序属于契约时才断言列表顺序；否则可以比较集合。不要把多个无关行为塞进一个测试，因为第一个断言失败后，后续断言不会执行。

## 5. 参数化：同一规则，多组输入

当多组输入验证同一规则时，使用 `pytest.mark.parametrize`：

```python
import pytest


@pytest.mark.parametrize("query", ["RAG", "rag", " Rag "])
def test_search_normalizes_query(sample_documents, query):
    results = search_documents(sample_documents, query, request_id="test-request")

    assert results[0].document.title == "RAG Guide"
```

参数化减少重复，但参数集合应有清晰理由。不要把正常、异常、日志和外部服务等完全不同的行为压缩成一张难读的大表。

## 6. Fixture：准备可复用的测试条件

fixture 为测试提供数据或资源，并由 pytest 管理生命周期：

```python
import pytest


@pytest.fixture
def sample_documents():
    return [
        Document(title="RAG Guide", content="retrieval", source="rag.md"),
        Document(title="Logging", content="events", source="logging.md"),
    ]
```

测试通过同名参数请求 fixture。fixture 适合复用有含义的测试条件、临时数据库连接或需要清理的资源；不应隐藏测试真正关心的输入。若读者必须跳转五个 fixture 才知道测试数据是什么，测试已经失去可读性。

测试文件系统时使用内置 `tmp_path`，不要写入仓库固定目录：

```python
def test_loads_utf8_text(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text("# RAG", encoding="utf-8")

    assert load_text(path) == "# RAG"
```

pytest 会为测试创建独立临时目录，降低测试之间互相污染的风险。

## 7. 验证异常和日志

使用 `pytest.raises` 验证明确的失败契约：

```python
import pytest


def test_empty_query_is_rejected(sample_documents):
    with pytest.raises(ValueError, match="query must not be empty"):
        search_documents(sample_documents, " ", request_id="req-test")
```

只写 `with pytest.raises(Exception)` 范围太宽，拼写错误或其他缺陷也可能让测试错误通过。

pytest 的 `caplog` 能捕获 `LogRecord`。对稳定的事件字段进行断言，不要绑定时间戳或整行展示格式：

```python
import logging


def test_empty_query_writes_warning(sample_documents, caplog):
    with caplog.at_level(logging.WARNING, logger="engineering_foundations.search"):
        with pytest.raises(ValueError):
            search_documents(sample_documents, "", request_id="req-test")

    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert record.event == "search_rejected"
    assert record.request_id == "req-test"
```

只为具有运维意义的日志写断言。把每条 `INFO` 文案都锁死会让正常文案调整导致大量测试失败。

## 8. 替身与 Mock：只隔离真正的边界

当代码调用付费模型 API、真实网络、系统时间或发送邮件时，单元测试应使用可控替身。最简单的方式通常是传入一个小函数或对象：

```python
def answer_question(question: str, model_client) -> str:
    return model_client.generate(question)


class FakeModelClient:
    def generate(self, question: str) -> str:
        return "fixed answer"
```

Fake 有可运行的简化实现；stub 返回预设值；mock 通常还验证调用方式。入门阶段名称不如边界重要：测试不应访问真实付费 API，也不应因为没有网络而随机失败。

不要 mock 被测模块内部每个函数。这样的测试只是在复述当前实现，重构代码即使行为不变也会失败。优先断言返回值、状态变化、对外调用和必要日志等可观察行为。

使用 `unittest.mock.patch` 时，应 patch 被测模块实际查找名称的位置，而不是对象最初定义的位置。若很难找到正确 patch 点，通常说明依赖没有被清晰地注入边界。

## 9. 让测试保持确定、独立和快速

可靠测试应满足：

- 确定：相同代码和输入得到相同结果，不依赖真实当前时间、随机数或网络波动。
- 独立：任意顺序运行都能通过，不依赖另一个测试先创建状态。
- 快速：开发者愿意频繁运行；慢测试可以单独分组。
- 可读：失败输出能说明哪项行为变化。
- 可重复：本地和 CI 使用项目声明的相同依赖与命令。

常见不稳定来源包括固定端口、共享文件、真实睡眠、未设种子的随机值、依赖测试顺序、时区差异和最终一致的外部系统。解决办法是注入时钟或随机源、使用 `tmp_path`、分配临时资源、等待明确条件以及把真实外部依赖放到受控集成环境，而不是失败后盲目重跑。

## 10. 覆盖率、CI 与失败处理

覆盖率说明哪些代码在测试期间被执行，不说明断言是否正确，也不说明需求是否完整。它适合发现从未经过测试的高风险区域，不适合作为唯一质量目标。一个没有断言却执行所有代码的测试也可能达到很高覆盖率。

提交前至少运行格式化、Lint 和测试：

```shell
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

CI 应从干净环境执行同样命令。测试失败时先阅读第一个相关 traceback，复现单个失败，再判断是产品缺陷、测试预期错误，还是测试环境问题。不要直接删除断言或标记跳过来换取绿色结果。

修复缺陷时，先添加能稳定复现缺陷的回归测试，确认它在修复前失败、修复后通过。这样同一种问题以后再次出现时能被自动发现。

## 11. 练习与验收

在[配套项目](../../projects/engineering-foundations/README.md)中完成：

1. 运行现有测试并用 `-k` 只选择空查询测试。
2. 使用参数化补充前后空格和混合大小写输入。
3. 为 `limit=0` 和负数添加失败测试，再实现清晰的校验。
4. 使用 `tmp_path` 编写一个从 Markdown 文件加载文档的测试。
5. 增加一个假搜索后端，让测试无需网络就能模拟超时和空结果。
6. 为修复过的一个缺陷保留回归测试，并在测试名中描述原始失败条件。

完成标准：整套测试能在干净环境一条命令运行；每个测试可以单独运行；不访问真实网络、不依赖执行顺序；失败输出能够定位到具体行为。

完成后回到[通用工程基础](index.md)检查整体完成标准。

## 延伸阅读

- [pytest 入门](https://docs.pytest.org/en/stable/getting-started.html)
- [pytest fixture 指南](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [pytest 参数化](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [pytest 日志捕获与 caplog](https://docs.pytest.org/en/stable/how-to/logging.html)
