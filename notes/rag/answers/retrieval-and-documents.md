---
title: 文档与关键词检索练习回答
type: answer
area: rag
status: learning
created: 2026-11-07
updated: 2026-11-07
tags:
  - rag
  - retrieval
  - answers
---

# 文档与关键词检索练习回答

本文记录[文档与关键词检索](../retrieval-and-documents.md)课程任务 1、任务 2 的验收结果与实际语料试查观察。可运行代码、语料、参数说明和测试命令保存在 [RAG Knowledge Base 项目](../../../projects/rag-knowledge-base/README.md)中。

下列运行命令均在配套项目的根目录执行。

## 任务 1 验收记录

2026-11-04 完成以下核对。

- 使用 `uv run --offline --no-sync rag-knowledge-base data/docs` 实际载入 50 篇文档，列出的编号与语料文件逐一对应。
- 重复读取完整语料，两次结果的编号、标题、正文和来源一致，50 篇正文均非空且各不相同。
- 从命令行逐个查询全部 50 个编号，展示的标题、来源和正文均与文件一致。模块入口和根目录脚本入口也能载入完整语料。
- 21 项自动化测试全部通过。小目录测试覆盖增加文件后已有记录保持一致、空文件跳过与原因日志，以及读取和解码失败。命令行测试覆盖按编号查看和失败退出。
- 原有三个手算样本保留，新增短文的出处与练习使用范围记录在[语料说明](../../../projects/rag-knowledge-base/data/README.md)。

## 任务 2 验收记录

2026-11-07 完成关键词检索入口的行为、自动化检查与实际语料试查。

- 命令行接收语料目录、查询、方法和 K，返回文档编号、标题、来源、完整正文与分数。当前方法为 `keyword`，默认 K 为 5。
- 命令行测试使用课程的三篇教学文档，查询“请求超时”时返回 `超时.md`、`日志.md`，分数分别为 3、2，零分的 `预算.md` 不出现。
- 48 项自动化测试全部通过，覆盖词项切分与去重、大小写统一、单篇计分、同分排序、前 K 项截取、空结果和无效 K；命令行测试实际完成文件加载、检索和展示。原有列表与按编号查看用例也通过。
- Python 格式化与 Ruff lint 通过，项目说明的 Markdown 格式化与 lint 通过。
- 使用完整的 50 篇语料，通过命令行入口执行以下三个查询，方法固定为 `keyword`，K 固定为 5。三个命令均正常退出，返回排名与分数记录如下。

### 试查 1：请求超时后为什么要限制重试次数

在项目目录执行：

```shell
.venv/bin/rag-knowledge-base data/docs --query "请求超时后为什么要限制重试次数" --method keyword --k 5
```

| 排名 | 文档编号与原文                                                                                              | 分数 |
| ---- | ----------------------------------------------------------------------------------------------------------- | ---- |
| 1    | [超时.md](../../../projects/rag-knowledge-base/data/docs/超时.md)                                           | 5    |
| 2    | [requests/request-timeout.md](../../../projects/rag-knowledge-base/data/docs/requests/request-timeout.md)   | 4    |
| 3    | [requests/retry-limit.md](../../../projects/rag-knowledge-base/data/docs/requests/retry-limit.md)           | 4    |
| 4    | [requests/retryable-errors.md](../../../projects/rag-knowledge-base/data/docs/requests/retryable-errors.md) | 4    |
| 5    | [output/tool-round-limit.md](../../../projects/rag-knowledge-base/data/docs/output/tool-round-limit.md)     | 3    |

最高分的短文只给出“请求超时后有限重试”的原则。它命中“请求、求超、超时、时后、重试”五个词项，但没有展开解释限制次数的原因。第三名的文档更具体地说明了最大尝试次数、剩余时间和停止条件，对理解怎样控制重试更有帮助。

第二名主要说明等待范围，第四名说明哪些错误允许重试，第五名讨论工具处理的轮次限制。第五名命中“请求、限制、次数”，仍需根据原文区分工具轮次与请求重试。此次结果提供了相关资料，但最高分文档没有完整回答提问中的“为什么”。

### 试查 2：uv sync

在项目目录执行：

```shell
.venv/bin/rag-knowledge-base data/docs --query "uv sync" --method keyword --k 5
```

| 排名 | 文档编号与原文                                                                        | 分数 |
| ---- | ------------------------------------------------------------------------------------- | ---- |
| 1    | [python/uv-sync.md](../../../projects/rag-knowledge-base/data/docs/python/uv-sync.md) | 2    |

查询切分为 `uv` 和 `sync`，唯一结果命中这两个词项。原文直接说明该命令根据项目配置和锁定结果同步环境，并安装可安装的项目自身，内容与查询对应。虽然 K 为 5，程序只返回实际匹配的一篇文档。

### 试查 3：连接一直没回应

在项目目录执行：

```shell
.venv/bin/rag-knowledge-base data/docs --query "连接一直没回应" --method keyword --k 5
```

| 排名 | 文档编号与原文                                                                                            | 分数 |
| ---- | --------------------------------------------------------------------------------------------------------- | ---- |
| 1    | [requests/request-timeout.md](../../../projects/rag-knowledge-base/data/docs/requests/request-timeout.md) | 1    |

唯一结果命中“连接”这个词项。原文讨论建立连接、等待首个事件和等待后续事件时可能停住的情况，与这次查询有关。此次能找到相关资料依靠共有文字；“一直没回应”与“超时”的含义关系没有参与计分。低分结果也可能有用，仍需要阅读原文判断。

这三次试查只反映当前短文语料上的表现。词项命中数便于核对程序规则，具体资料是否有助于回答问题，需要结合原文判断。
