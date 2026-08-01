---
title: 日志基础
type: concept
area: engineering
status: learning
created: 2026-08-01
updated: 2026-08-01
tags:
  - engineering
  - logging
  - observability
  - python
---

# 日志基础

日志是程序运行期间产生的事件记录。它的目标不是“多打印一些内容”，而是让开发者能够回答：哪次操作失败、失败发生在哪个模块、当时有哪些安全且必要的上下文，以及故障影响了一个请求还是整个服务。

本课程使用 Python 标准库 `logging` 演示通用概念。其他语言的日志库名称不同，但事件、级别、上下文、输出目的地和敏感信息控制等原则相同。

## 1. 日志与 `print()` 的边界

`print()` 适合命令行程序面向用户的正常输出，例如搜索结果或导出文件的位置。日志面向开发、运维和审计，用于记录程序内部事件。

```python
print("找到 3 篇文档")
logger.info("search completed", extra={"result_count": 3})
```

两行内容看似相近，但用途不同：用户输出可以翻译、排版或通过管道交给其他命令；日志还需要级别、时间、模块名和请求标识，并可能被集中采集。不要用日志代替正常返回值，也不要只用 `print()` 报告后台故障。

异常与日志也不能互相替代。函数遇到无法完成的操作时，应通过返回值或异常把失败告诉调用者；日志只是记录这件事。只记一条 `ERROR` 后继续返回看似正常的空结果，会让调用者误判操作成功。

## 2. 把日志写成事件

一条有用日志通常包括：

| 字段           | 作用                               | 示例                        |
| -------------- | ---------------------------------- | --------------------------- |
| `timestamp`    | 事件何时发生                       | `2026-08-01T08:15:30Z`      |
| `level`        | 事件严重程度                       | `INFO`                      |
| `logger`       | 事件来自哪个模块                   | `engineering.search`        |
| `event`        | 稳定、可检索的事件名称             | `search_completed`          |
| `message`      | 给人阅读的简短说明                 | `search completed`          |
| `request_id`   | 把同一次操作的多条记录关联起来     | `req-7f31`                  |
| 业务上下文字段 | 解释事件但不暴露敏感信息的有限数据 | `result_count=3`            |
| 异常信息       | 错误类型和调用栈                   | `TimeoutError` 与 traceback |

“搜索失败”仍然太模糊。更可定位的事件应说明阶段和安全上下文：

```python
logger.error(
    "document parsing failed",
    extra={
        "event": "document_parse_failed",
        "request_id": request_id,
        "source_type": ".md",
    },
)
```

不要为了“上下文完整”记录查询全文、文档正文、Authorization 请求头、Cookie、API Key、身份证号或电子邮箱。日志往往保存时间长、访问面广，应默认把输入视为可能包含敏感信息。优先记录长度、数量、类别、稳定 ID 或经过批准的脱敏值。

## 3. 选择正确的日志级别

日志级别表达事件对系统的影响，而不是开发者当时的情绪。

| 级别       | 使用场景                             | 文档搜索示例                         |
| ---------- | ------------------------------------ | ------------------------------------ |
| `DEBUG`    | 仅排查问题时需要的细节               | 分词数量、候选文档得分               |
| `INFO`     | 正常业务里程碑                       | 搜索开始、搜索完成、索引加载成功     |
| `WARNING`  | 出现异常情况，但当前操作仍可受控处理 | 空查询被拒绝、单个损坏文档被跳过     |
| `ERROR`    | 当前功能或请求失败，但进程仍能继续   | 数据库超时导致本次搜索失败           |
| `CRITICAL` | 整个进程或核心能力可能无法继续       | 启动时关键配置损坏且没有安全降级方案 |

配置的级别是最低保留阈值。阈值为 `INFO` 时，会保留 `INFO`、`WARNING`、`ERROR` 和 `CRITICAL`，丢弃 `DEBUG`。可在[日志级别交互实验](../../projects/engineering-foundations/logging-lab/index.html)中切换阈值观察结果。

不要把用户输入校验失败一律记成 `ERROR`。如果系统正确拒绝了空查询，它是预期内的失败，通常使用 `WARNING` 或只返回明确的 4xx 错误。否则大量可预期事件会淹没真正的系统故障。

## 4. Python 日志的数据流

应用模块先通过 logger 创建 `LogRecord`。logger 和 handler 都可以按级别或 filter 筛选；handler 决定记录去往控制台、文件或集中采集器；formatter 决定最终文本或 JSON 结构。

![Python 日志从事件到输出的处理流程](assets/logging-pipeline.svg)

各模块只取得以模块名命名的 logger：

```python
import logging

logger = logging.getLogger(__name__)
```

程序入口统一配置 handler 和 formatter。不要让每个业务模块都调用 `basicConfig()` 或各自添加控制台 handler，否则容易出现重复日志和互相冲突的级别。Python logger 使用点分层级，`engineering.search` 的记录默认会向父 logger 传播，最终由上层 handler 处理。

## 5. 配置可读文本日志

小型命令行程序可以在入口处使用 `basicConfig()`：

```python
import logging


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"invalid log level: {level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
```

可变数据使用日志参数传入：

```python
logger.info("loaded %d documents", document_count)
```

不建议写成 `logger.info(f"loaded {document_count} documents")`。参数形式把消息模板与数据分开，而且日志级别被过滤时可以避免提前格式化。性能差异通常不是首要问题，稳定的事件模板和统一风格更重要。

## 6. 结构化日志与请求上下文

供人直接阅读的文本适合本地开发；生产服务常使用一行一个 JSON 对象，便于按字段筛选、聚合和告警：

```json
{
  "timestamp": "2026-08-01T08:15:30Z",
  "level": "INFO",
  "logger": "engineering.search",
  "event": "search_completed",
  "request_id": "req-7f31",
  "result_count": 3,
  "message": "search completed"
}
```

结构化日志不是把整段文本塞进 `message` 后就结束。需要检索的值应有稳定字段名，字段类型也应保持一致，例如 `duration_ms` 始终是数字而不是有时写成 `"23ms"`。

一次 HTTP 请求、后台任务或命令执行应在入口生成 `request_id`，随后传递给关键日志。入门阶段可以通过函数参数和 `extra` 显式传入：

```python
logger.info(
    "search completed",
    extra={
        "event": "search_completed",
        "request_id": request_id,
        "result_count": len(results),
    },
)
```

大型异步服务可以进一步使用 `LoggerAdapter`、filter 或 `contextvars` 自动补充上下文，但自动化之前必须先明确 ID 在何处生成、跨哪些边界传播、何时清除。否则上下文可能串到另一请求。

## 7. 正确记录异常

在 `except` 块中使用 `logger.exception()`，会自动附带当前异常的调用栈：

```python
try:
    index.refresh()
except TimeoutError:
    logger.exception(
        "index refresh timed out",
        extra={"event": "index_refresh_failed"},
    )
    raise
```

如果上层会统一记录并处理异常，下层不必先记录后重新抛出，否则同一个故障可能出现多条重复 `ERROR`。选择最了解业务上下文且真正决定“重试、降级还是终止”的边界记录一次。

不要使用 `logger.error("failed: %s", error)` 代替调用栈；字符串通常只有异常消息，缺少出错文件和调用路径。也不要无条件捕获 `Exception` 后继续运行，除非边界确实有明确的隔离或降级策略。

## 8. 文件日志、轮转与集中采集

本地脚本可以使用 `FileHandler` 或 `RotatingFileHandler`。长期运行的容器服务通常更适合把日志写到标准输出或标准错误，由运行平台负责采集、保留和轮转。应用自行写无限增长的文件，会带来磁盘耗尽、并发写入和容器实例销毁后日志丢失等问题。

无论输出到哪里，都应明确：

- 日志保存多久，谁可以读取。
- 时区是否统一，跨系统关联时通常使用 UTC。
- 单行大小和总量限制，是否需要采样高频 `DEBUG` 事件。
- 多进程或多实例如何集中采集。
- 敏感字段如何拦截、脱敏和审计。

日志、指标和 trace 是互补信号。日志解释离散事件，指标回答错误率和延迟趋势，trace 展示一次请求跨组件的调用链。不要把每个数值都做成日志，也不要期待仅凭指标还原具体失败上下文。

## 9. 常见反模式

- `except Exception: pass`：失败被吞掉，调用者和日志都得不到信号。
- 所有地方都调用根 logger：无法根据模块定位或配置。
- 每个模块都添加 handler：同一记录沿层级传播后重复输出。
- 在循环中记录大量 `INFO`：正常流量制造高成本噪声。
- 只写 `something went wrong`：没有事件阶段、ID 或异常调用栈。
- 记录完整对象：对象可能包含密钥、正文或不稳定表示。
- 通过日志判断业务成功：调用者仍应依赖返回值或异常。
- 测试精确时间戳或完整格式字符串：测试会与展示格式强耦合。

## 10. 练习与验收

在[配套项目](../../projects/engineering-foundations/README.md)基础上完成：

1. 运行文本格式和 JSON 格式的命令行演示，找出相同事件在两种格式中的对应字段。
2. 在交互实验中分别选择 `DEBUG`、`INFO` 和 `ERROR`，解释每次被过滤的事件。
3. 为“没有搜索结果”增加一条合理级别的日志，但不记录原始查询文本。
4. 模拟一次外部检索超时，只在决定终止本次请求的边界使用 `logger.exception()`。
5. 使用 pytest `caplog` 断言空查询产生 `WARNING`、事件名和同一个 `request_id`。

完成标准：给定一条失败日志，可以通过事件名、模块、级别和请求 ID 定位到代码阶段；调整级别不需要修改业务模块；日志中不包含密钥、完整查询或文档正文。

完成后继续学习[基础测试](basic-testing.md)。

## 延伸阅读

- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html)
- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [Python LogRecord 属性](https://docs.python.org/3/library/logging.html#logrecord-attributes)
