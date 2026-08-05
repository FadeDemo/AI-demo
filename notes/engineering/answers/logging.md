---
title: 日志基础练习回答
type: answer
area: engineering
status: completed
created: 2026-08-03
updated: 2026-08-05
tags:
  - engineering
  - logging
  - answers
---

# 日志基础练习回答

本文记录[日志基础](../logging.md)课程“练习与验收”第 1、2 项的稳定观察结论。命令运行、页面操作、代码修改和测试等实操不在此重复记录；每次运行都会变化的时间戳和 `request_id` 也不作为留档内容。

## 文本日志与 JSON 日志的字段对应

文本格式和 JSON 格式改变的是日志展示方式，不是业务事件本身。以 `search_started` 或 `search_completed` 事件为例，对应关系如下：

| 含义        | 文本日志中的位置或形式                             | JSON 日志中的字段 |
| ----------- | -------------------------------------------------- | ----------------- |
| 时间        | 行首的 UTC 时间                                    | `timestamp`       |
| 级别        | 时间后的 `INFO`                                    | `level`           |
| logger 名称 | `engineering_foundations.search`                   | `logger`          |
| 事件名      | `event=search_started` 或 `event=search_completed` | `event`           |
| 请求标识    | `request_id=<value>`                               | `request_id`      |
| 消息        | 文本行末的 `search started` 或 `search completed`  | `message`         |

文本 formatter 把选定字段排成一行，适合人直接阅读；JSON formatter 把字段保存为独立键值，还会保留 `document_count`、`query_length`、`result_count` 和 `duration_ms` 等结构化上下文，更便于机器解析、筛选和统计。

同一次命令中的 `search_started` 和 `search_completed` 共享一个 `request_id`。两条演示命令是两次独立运行，会各自生成新 ID，因此不要求文本日志和 JSON 日志中的 ID 字面值相同。命令行搜索结果由 `print()` 写到 stdout，日志由 handler 写到 stderr；它们默认同时显示在终端，但仍是两个独立的输出流。

## 最低日志级别的过滤结果

日志级别交互实验中的“正常搜索”场景产生 3 条记录：`INFO` 级别的 `search_started`、`DEBUG` 级别的 `candidate_scored` 和 `INFO` 级别的 `search_completed`。

| 最低保留级别 | 保留数量 | 被过滤数量 | 被过滤的事件                                             |
| ------------ | -------: | ---------: | -------------------------------------------------------- |
| `DEBUG`      |        3 |          0 | 无                                                       |
| `INFO`       |        2 |          1 | `candidate_scored`                                       |
| `ERROR`      |        0 |          3 | `search_started`、`candidate_scored`、`search_completed` |

配置级别表示最低保留阈值，会保留等于或高于该阈值的记录。因此 `DEBUG` 保留全部记录；`INFO` 过滤严重程度更低的 `DEBUG` 记录；`ERROR` 会过滤正常搜索场景中的 `DEBUG` 和 `INFO` 记录。

## 根据影响选择日志级别

日志级别描述事件对当前操作和系统继续运行能力的影响，而不是简单区分“成功”与“失败”：

| 级别       | 选择标准                                         | 本课或相近场景中的例子                           |
| ---------- | ------------------------------------------------ | ------------------------------------------------ |
| `DEBUG`    | 仅在诊断时需要的细节，正常运行通常可以过滤       | 单篇候选文档的评分过程                           |
| `INFO`     | 正常业务流程中的重要里程碑                       | 搜索开始、搜索完成，以及受控的无结果搜索         |
| `WARNING`  | 出现异常输入或局部问题，但系统已按预期处理       | 拒绝空查询、拒绝小于 1 的 `limit`                |
| `ERROR`    | 当前请求或功能失败，但进程和其他请求仍可继续     | 外部索引超时导致本次搜索终止                     |
| `CRITICAL` | 核心能力或整个进程无法安全继续，并且没有降级方案 | 启动时关键配置损坏，导致服务无法提供基本搜索能力 |

空查询和非法 `limit` 虽然会使当前调用返回 `ValueError`，但这是程序正确执行输入校验后的受控结果，因此使用 `WARNING`，不应仅因为出现异常就一律记录为 `ERROR`。只有当前请求确实因系统故障失败时才使用 `ERROR`；只有故障影响整个进程或核心能力时才使用 `CRITICAL`。

## Python 日志组件的职责

- logger 是业务代码记录事件的入口，也代表日志来源。它接收 `debug()`、`info()` 等调用，并根据 logger 级别和 filter 判断记录是否继续处理。
- `LogRecord` 是一次日志事件在程序内部的数据对象，保存时间、级别、logger 名称、消息，以及通过 `extra` 附加的 `event`、`request_id` 等结构化字段。
- handler 接收通过筛选的 `LogRecord`，决定把它发送到标准错误、文件或远程系统等目的地。不同 handler 可以设置不同的最低级别。
- formatter 把 `LogRecord` 转换为最终展示格式，例如一行可读文本或一个 JSON 对象；它不负责选择输出目的地。

本项目在业务模块中通过命名 logger 创建记录，记录沿层级传播给入口配置的 root logger。root logger 上的 `StreamHandler` 接收记录，formatter 将其转换为文本或 JSON，最后 handler 默认写入标准错误。这个顺序可以概括为：业务代码调用 logger，logger 创建 `LogRecord`，handler 接收记录，formatter 格式化记录，handler 输出结果。

## request_id 的生成与安全边界

命令行入口在每次执行时调用 `uuid4()` 生成一个新的 `request_id`。入口将它作为普通函数参数传给 `search_documents()`；搜索函数记录事件时，再通过 `extra` 把同一个值添加到各条 `LogRecord`。因此一次搜索的 `search_started`、`search_completed`、拒绝事件或无结果事件可以用同一个 ID 关联，不需要记录原始查询内容。

日志通常保存时间长、复制到集中平台，并可能被开发、运维或审计人员检索。如果写入 API Key、个人信息或完整文档，凭据可能被滥用，个人隐私和受保护内容也可能通过日志副本扩大泄露范围。删除业务数据库中的内容也不一定会同步删除历史日志。因此本项目只记录查询长度、文档数量、结果数量、事件名、稳定 ID 和耗时等诊断所需字段，不记录原始查询、文档正文或密钥。`request_id` 只用于关联事件，也不应编码个人信息或其他敏感内容。
