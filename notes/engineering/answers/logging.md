---
title: 日志基础练习回答
type: answer
area: engineering
status: completed
created: 2026-08-03
updated: 2026-08-03
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

“正常搜索”场景产生 3 条记录：`INFO` 级别的 `search_started`、`DEBUG` 级别的 `candidate_scored` 和 `INFO` 级别的 `search_completed`。

| 最低保留级别 | 保留数量 | 被过滤数量 | 被过滤的事件                                             |
| ------------ | -------: | ---------: | -------------------------------------------------------- |
| `DEBUG`      |        3 |          0 | 无                                                       |
| `INFO`       |        2 |          1 | `candidate_scored`                                       |
| `ERROR`      |        0 |          3 | `search_started`、`candidate_scored`、`search_completed` |

配置级别表示最低保留阈值，会保留等于或高于该阈值的记录。因此 `DEBUG` 保留全部记录；`INFO` 过滤严重程度更低的 `DEBUG` 记录；`ERROR` 会过滤正常搜索场景中的 `DEBUG` 和 `INFO` 记录。
