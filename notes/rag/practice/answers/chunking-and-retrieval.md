---
title: 文档切块与片段检索任务 2 验收记录
type: answer
area: rag
status: learning
created: 2026-11-23
updated: 2026-11-23
tags:
  - rag
  - chunking
  - retrieval
  - answers
---

# 文档切块与片段检索任务 2 验收记录

这份记录对应课程的任务 2。[文档切块与片段检索](../chunking-and-retrieval.md)

## 离线回归

默认回归有 149 项测试通过，另有 1 项真实模型集成测试按默认设置跳过。Ruff 格式检查和 lint 均通过。

命令行用例从 `--query` 发起查询，用模型替身给出固定向量。用例确认同一文档的两个片段能按分数返回，同一次命令中的多个查询共用一批片段向量。超长输入进入长度检查后，程序报出超限原因，模型的 `encode` 调用次数为零。维度错误的向量会在计算相似度前被拒绝。[命令行测试](../../../../projects/rag-knowledge-base/tests/test_cli.py)

## 真实模型试查

本次用 Sentence Transformers 从缓存加载 `intfloat/multilingual-e5-small`，在 CPU 上运行，模型修订为 `fd1525a9fd15316a2d503bf26ab031a61d056e98`。`v1` 语料有 50 篇文档。块长上限为 100 个 Unicode 码点，相邻块重叠 20 个码点，共得到 98 块。每个问题保留前两条结果。

在 RAG 项目目录执行下面的命令。[项目运行说明](../../../../projects/rag-knowledge-base/README.md#环境与运行)

```shell
HF_HUB_OFFLINE=1 uv run --no-sync rag-knowledge-base data/docs --method vector --k 2 \
  --query "重试次数上限" \
  --query "怎样记录请求耗时？" \
  --query "发送前怎样检查上下文长度？"
```

六条结果的正文都与各自文档的对应切片一致。下面保留命令的原始查询输出。

```text
查询 重试次数上限
编号为 {"doc_id": "requests/retry-limit.md", "document_version": "v1", "chunk_size": 100, "overlap": 20, "start": 0, "end": 100} 的chunk，标题是 retry-limit，内容是 # 重试次数需要上限

本课程把首次发送也计入最大尝试次数。最大尝试次数为三次时，持续失败最多允许首次请求加两次重试。

每次重试继续使用同一逻辑请求的剩余时间。尝试次数用完、总期限到达或用户取消后，，来源是 requests/retry-limit.md，匹配得分：0.9151814653347856，区间是 [0, 100)
编号为 {"doc_id": "output/tool-round-limit.md", "document_version": "v1", "chunk_size": 100, "overlap": 20, "start": 0, "end": 100} 的chunk，标题是 tool-round-limit，内容是 # 限制连续工具处理

工具结果回传后，模型可能继续请求其他工具。应用循环处理时，需要设置轮次或调用次数上限，并在每次发送与执行前检查停止条件。

达到上限、用户取消或总期限耗尽时，应停止后续操作。测，来源是 output/tool-round-limit.md，匹配得分：0.8767889611089782，区间是 [0, 100)
查询 怎样记录请求耗时？
编号为 {"doc_id": "\u65e5\u5fd7.md", "document_version": "v1", "chunk_size": 100, "overlap": 20, "start": 0, "end": 18} 的chunk，标题是 日志，内容是 # 日志

记录请求耗时与超时类别。，来源是 日志.md，匹配得分：0.9184802131616462，区间是 [0, 18)
编号为 {"doc_id": "engineering/timing-logs.md", "document_version": "v1", "chunk_size": 100, "overlap": 20, "start": 80, "end": 119} 的chunk，标题是 timing-logs，内容是 束的过程，重试等待也包含在内。没有展示正文的失败请求，应把首段耗时记录为缺失。，来源是 engineering/timing-logs.md，匹配得分：0.9088938485340003，区间是 [80, 119)
查询 发送前怎样检查上下文长度？
编号为 {"doc_id": "\u9884\u7b97.md", "document_version": "v1", "chunk_size": 100, "overlap": 20, "start": 0, "end": 17} 的chunk，标题是 预算，内容是 # 预算

发送前检查上下文长度。，来源是 预算.md，匹配得分：0.9223064729433478，区间是 [0, 17)
编号为 {"doc_id": "requests/retry-limit.md", "document_version": "v1", "chunk_size": 100, "overlap": 20, "start": 80, "end": 110} 的chunk，标题是 retry-limit，内容是 。尝试次数用完、总期限到达或用户取消后，应用应停止后续发送。，来源是 requests/retry-limit.md，匹配得分：0.8892951338941714，区间是 [80, 110)
```

## 原文核对

「重试次数上限」可用第一条结果作答。原文 `[12, 59)` 把首次发送算进尝试次数，并举出了首次发送加两次重试的例子。排第二的片段讨论工具调用轮次。[重试次数需要上限](../../../../projects/rag-knowledge-base/data/docs/requests/retry-limit.md)

「怎样记录请求耗时」的第一条提醒记录耗时和超时类别。第二条补充了重试等待计入总耗时，以及失败请求未展示正文时如何记录首段耗时。要查清两种耗时怎么算，可以读原文 `[12, 67)` 和 `[69, 119)`。前一段定义首段耗时，后一段说明总耗时与失败记录。[记录首段与总耗时](../../../../projects/rag-knowledge-base/data/docs/engineering/timing-logs.md)

「发送前怎样检查上下文长度」的第一条给出了检查提示，第二条讲重试何时停止。具体做法要回查上下文窗口一文。`[12, 63)` 说明应把实际发送的输入和计划输出一起算进窗口，`[65, 127)` 给出超出容量时的处理办法。[上下文窗口的容量](../../../../projects/rag-knowledge-base/data/docs/context/context-window.md)

## 切块边界

重试文档的 `[0, 100)` 停在「用户取消后，」。接下来的 `[100, 110)` 才给出动作「应用应停止后续发送。」相邻片段 `[80, 110)` 保留了完整的条件和动作。读到第一块时可以确认尝试次数的例子。要核对停止规则，可以沿来源回查相邻片段。[重试次数需要上限](../../../../projects/rag-knowledge-base/data/docs/requests/retry-limit.md)
