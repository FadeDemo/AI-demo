---
title: 结构化输出练习回答
type: answer
area: llm
status: learning
created: 2026-09-03
updated: 2026-09-10
tags:
  - llm
  - json-schema
  - answers
---

# 结构化输出练习回答

本文记录[结构化输出](../structured-output.md)课程的书面回答。可运行的 Schema、验证流水线和验收测试保存在 [LLM Terminal Assistant 项目](../../../projects/llm-terminal-assistant/README.md)中。

## 任务 1：定义学习卡片 Schema

Schema 保存在 [`study-card.schema.json`](../../../projects/llm-terminal-assistant/schemas/study-card.schema.json)。它将 `title`、`summary`、`questions` 和 `source_ids` 全部定义为必填字段，并使用 `additionalProperties: false` 拒绝未声明的额外字段。

`source_ids` 至少包含一个非空字符串，并使用标准 JSON Schema 的 `uniqueItems: true` 拒绝重复 ID。确认每个 ID 是否属于本次输入的来源允许集合属于业务规则，由任务 2 的验证流水线实现，不属于任务 1 的 Schema 验收范围。

项目使用默认离线的自动化测试验证 Schema 本身合法，合法学习卡片能通过，并且缺少必填字段、空标题、问题数量越界、字段类型错误、额外字段、空来源 ID 和重复来源 ID 都会被拒绝。
