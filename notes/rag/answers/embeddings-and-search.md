---
title: Embedding 与逐篇检索练习记录
type: answer
area: rag
status: completed
created: 2026-11-10
updated: 2026-11-12
tags:
  - rag
  - embedding
  - semantic-search
  - answers
---

# Embedding 与逐篇检索练习记录

本文记录[Embedding 与逐篇检索](../embeddings-and-search.md)任务 1、任务 2 的实现验收、离线测试、真实模型运行结果、两种检索方法的试查观察及知识检查参考回答。配套代码位于 [RAG Knowledge Base 项目](../../../projects/rag-knowledge-base/README.md)。

## 任务 1 验收结果

2026-11-10 完成任务 1 验收。

- 文档编码复用已有文档记录，将生成的向量与文档编号对应保存。任一文档超长或生成非法向量时，本次调用抛出异常。
- 查询和文档编码完成后，检查空向量、零向量、非数字、布尔值、NaN、无穷大和维度不符。输出维度通过 Sentence Transformers 模型对象的 `get_embedding_dimension()` 获取。
- 离线替身记录完整输入和编码参数，覆盖前缀、归一化、返回格式、编号对应、长度边界，以及批量处理中前一篇成功、后一篇失败的场景。
- 真实模型先完成三篇固定文档和三条问题的编码，再准备完整语料。50 篇文档生成 50 条向量，返回编号集合与文档编号集合一致，所有向量均为 384 维。

## 模型和运行配置

本次通过 Sentence Transformers Python 库加载 Hugging Face 上的 `intfloat/multilingual-e5-small`，将模型固定到已核对的提交。[模型文件与修订版本](https://huggingface.co/intfloat/multilingual-e5-small/tree/fd1525a9fd15316a2d503bf26ab031a61d056e98)

| 配置项           | 本次运行值                                 |
| ---------------- | ------------------------------------------ |
| 模型             | `intfloat/multilingual-e5-small`           |
| 模型修订         | `fd1525a9fd15316a2d503bf26ab031a61d056e98` |
| 运行设备         | CPU                                        |
| 输出维度         | 384                                        |
| 单条输入长度上限 | 512 Token                                  |
| 问题前缀         | `"query: "`                                |
| 文档前缀         | `"passage: "`                              |
| 归一化           | 两侧均传入 `normalize_embeddings=True`     |

两个前缀的末尾都包含一个空格。文档完整输入依次由前缀、标题、换行和正文组成。应用用配套分词器在 `truncation=False` 时取得完整 Token 编号序列，数量超过模型的 `max_seq_length` 时报错并给出文档编号。

运行环境为 Python 3.13.9、sentence-transformers 6.2.0、transformers 5.22.2、torch 2.15.0 和 NumPy 2.5.4。

## 离线测试

任务 1 验收时，默认套件发现 72 项测试，其中 71 项通过，1 项真实模型集成测试按默认设置跳过。编码组件的离线测试使用能记录调用的模型替身，替身同时提供编码结果、分词结果和声明的输出维度。

非法编码结果的测试检查具体错误类别，并确认测试输入实际经过了编码调用。维度切换用例将替身声明的输出维度改为 3，问题和文档都能正常返回三维向量。

相似度测试覆盖独立比较接口的输入保护，并直接验证纯计算函数的结果及其调用记录。

## 真实模型运行结果

显式启用[真实模型集成测试](../../../projects/rag-knowledge-base/tests/test_embedding_integration.py)，用固定的三篇文档与三条问题调用项目编码函数。文档通过已有加载函数读取，向量通过 `encode_documents` 和 `encode_query` 生成。

下表范数保留 12 位小数，测试以 `1e-5` 为容差检查单位长度。

| 输入类别 | 输入                       | 向量维度 | 范数           |
| -------- | -------------------------- | -------- | -------------- |
| 文档     | 超时.md                    | 384      | 1.000000051147 |
| 文档     | 日志.md                    | 384      | 1.000000036569 |
| 文档     | 预算.md                    | 384      | 0.999999999247 |
| 问题     | 请求一直没有返回怎么办？   | 384      | 0.999999997006 |
| 问题     | 怎样记录请求耗时？         | 384      | 1.000000004111 |
| 问题     | 发送前怎样检查上下文长度？ | 384      | 0.999999919858 |

固定样本验证通过后，沿用同一个模型读取并编码完整语料。实际读取 50 篇文档，得到 50 条 384 维向量，全部通过现有输入长度与向量检查。

本次先下载模型，再用缓存离线运行包含整批准备的集成测试，1 项通过。模型文件保存在仓库根目录的 `.cache/huggingface/`。

## 复现命令

以下命令均在配套项目目录执行。

命令中的 `HF_HUB_OFFLINE=1` 是 Hugging Face Hub 库的离线设置，启用后使用本地模型缓存。默认离线测试按下面的命令运行。

```shell
HF_HUB_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

设置 `RAG_RUN_REAL_EMBEDDING_TESTS=1` 后，测试会加载固定模型。首次运行会下载模型文件。

```shell
RAG_RUN_REAL_EMBEDDING_TESTS=1 .venv/bin/python -m unittest discover -s tests -p 'test_embedding_integration.py' -v
```

模型缓存可用后，使用下面的命令离线复测。

```shell
RAG_RUN_REAL_EMBEDDING_TESTS=1 HF_HUB_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -p 'test_embedding_integration.py' -v
```

## 任务 2 验收结果

2026-11-11 完成任务 2 验收。

- 同一命令行入口通过 `--method keyword` 或 `--method vector` 选择方法。两种方法都展示文档编号、标题、完整正文、来源和分数，按分数降序排列，同分按编号升序排列，再取前 K 项。
- `--query` 可以重复提供。向量分支在查询循环前加载模型、生成整批文档向量，每个问题复用这批向量。多个问题的结果按查询标题分组，单问题调用继续使用原有展示格式。
- 空白查询和空语料返回空结果，查询编码调用次数为零。非法 K、文档编号集合不符，以及编码结果为零向量、含非有限数值或维度不符等情况，都有离线测试验证错误原因和执行边界。
- 默认离线套件发现 89 项测试，88 项通过，1 项真实模型集成测试按默认设置跳过。三项多问题入口测试验证各组的编号、分数和展示字段，并记录模型调用，确认三条正常查询只加载一次模型、每篇文档只编码一次。
- 真实语料试查沿用任务 1 的三个问题，K 取 5。关键词和向量方法各通过一次命令行调用处理三个问题，向量调用一次准备 50 篇文档后连续查询。两次调用均正常退出，30 条结果涉及 17 篇原文，返回的标题、正文和来源均与原文一致。

## 任务 2 真实语料对比

本次向量试查使用上文记录的固定模型修订、CPU 和归一化设置，通过本地缓存离线运行。运行环境版本与任务 1 相同。每种方法分别保留前五项，关键词分数是共同词项个数，向量分数是余弦相似度。下表中的向量分数保留六位小数，排名沿用程序输出。

### 试查 1　请求一直没有返回怎么办？

| 方法   | 排名 | 文档                                                                                                        | 分数     |
| ------ | ---- | ----------------------------------------------------------------------------------------------------------- | -------- |
| 关键词 | 1    | [context/request-budget.md](../../../projects/rag-knowledge-base/data/docs/context/request-budget.md)       | 2        |
| 关键词 | 2    | [engineering/timing-logs.md](../../../projects/rag-knowledge-base/data/docs/engineering/timing-logs.md)     | 2        |
| 关键词 | 3    | [output/schema-validation.md](../../../projects/rag-knowledge-base/data/docs/output/schema-validation.md)   | 2        |
| 关键词 | 4    | [requests/fake-client.md](../../../projects/rag-knowledge-base/data/docs/requests/fake-client.md)           | 2        |
| 关键词 | 5    | [context/context-window.md](../../../projects/rag-knowledge-base/data/docs/context/context-window.md)       | 1        |
| 向量   | 1    | [超时.md](../../../projects/rag-knowledge-base/data/docs/超时.md)                                           | 0.891825 |
| 向量   | 2    | [requests/retryable-errors.md](../../../projects/rag-knowledge-base/data/docs/requests/retryable-errors.md) | 0.888998 |
| 向量   | 3    | [requests/retry-limit.md](../../../projects/rag-knowledge-base/data/docs/requests/retry-limit.md)           | 0.887992 |
| 向量   | 4    | [requests/finish-reason.md](../../../projects/rag-knowledge-base/data/docs/requests/finish-reason.md)       | 0.887345 |
| 向量   | 5    | [output/stream-failure.md](../../../projects/rag-knowledge-base/data/docs/output/stream-failure.md)         | 0.885196 |

关键词前四名都只有两个共同词项。`context/request-budget.md` 与问题共同包含“请求”和“没有”，内容讲的是发送前预算检查。`output/schema-validation.md` 命中“求一”和“返回”，其中“求一”来自“要求一个”，全文讨论结构校验。这些匹配没有提供等待请求返回时的处理办法。

向量方法找到了超时、错误分类与重试上限的资料。`超时.md` 只给出有限重试的原则，第二、第三名进一步说明重试条件、剩余时间和停止条件。第四名讲响应结束后的判断，第五名讲已经展示部分正文后的中断，与持续没有返回的情形关系较弱。直接说明连接、首个事件和后续事件等待上限的 `requests/request-timeout.md` 在本问题的两种结果中都排在前五名之外。[等待上限原文](../../../projects/rag-knowledge-base/data/docs/requests/request-timeout.md)

### 试查 2　怎样记录请求耗时？

| 方法   | 排名 | 文档                                                                                                                      | 分数     |
| ------ | ---- | ------------------------------------------------------------------------------------------------------------------------- | -------- |
| 关键词 | 1    | [日志.md](../../../projects/rag-knowledge-base/data/docs/日志.md)                                                         | 5        |
| 关键词 | 2    | [engineering/timing-logs.md](../../../projects/rag-knowledge-base/data/docs/engineering/timing-logs.md)                   | 3        |
| 关键词 | 3    | [context/history-growth.md](../../../projects/rag-knowledge-base/data/docs/context/history-growth.md)                     | 2        |
| 关键词 | 4    | [context/request-budget.md](../../../projects/rag-knowledge-base/data/docs/context/request-budget.md)                     | 2        |
| 关键词 | 5    | [engineering/credential-redaction.md](../../../projects/rag-knowledge-base/data/docs/engineering/credential-redaction.md) | 2        |
| 向量   | 1    | [日志.md](../../../projects/rag-knowledge-base/data/docs/日志.md)                                                         | 0.918480 |
| 向量   | 2    | [engineering/timing-logs.md](../../../projects/rag-knowledge-base/data/docs/engineering/timing-logs.md)                   | 0.910735 |
| 向量   | 3    | [超时.md](../../../projects/rag-knowledge-base/data/docs/超时.md)                                                         | 0.888958 |
| 向量   | 4    | [requests/request-timeout.md](../../../projects/rag-knowledge-base/data/docs/requests/request-timeout.md)                 | 0.883229 |
| 向量   | 5    | [requests/rate-limit.md](../../../projects/rag-knowledge-base/data/docs/requests/rate-limit.md)                           | 0.879957 |

两种方法的前两名一致。`日志.md` 简要说明记录请求耗时与超时类别，`engineering/timing-logs.md` 进一步说明首段耗时从何时计算、总耗时是否包含重试等待，以及没有展示正文的失败请求怎样记录首段耗时。第二篇提供了更具体的实现依据。[耗时记录原文](../../../projects/rag-knowledge-base/data/docs/engineering/timing-logs.md)

后续结果各有偏离。关键词方法带回历史增长、请求预算和日志脱敏，向量方法带回超时重试、等待范围和限流。这些资料与请求处理有关，正文提供的耗时记录规则较少。

### 试查 3　发送前怎样检查上下文长度？

| 方法   | 排名 | 文档                                                                                                    | 分数     |
| ------ | ---- | ------------------------------------------------------------------------------------------------------- | -------- |
| 关键词 | 1    | [预算.md](../../../projects/rag-knowledge-base/data/docs/预算.md)                                       | 8        |
| 关键词 | 2    | [context/context-window.md](../../../projects/rag-knowledge-base/data/docs/context/context-window.md)   | 4        |
| 关键词 | 3    | [context/history-growth.md](../../../projects/rag-knowledge-base/data/docs/context/history-growth.md)   | 3        |
| 关键词 | 4    | [context/request-budget.md](../../../projects/rag-knowledge-base/data/docs/context/request-budget.md)   | 3        |
| 关键词 | 5    | [context/history-pruning.md](../../../projects/rag-knowledge-base/data/docs/context/history-pruning.md) | 2        |
| 向量   | 1    | [预算.md](../../../projects/rag-knowledge-base/data/docs/预算.md)                                       | 0.922306 |
| 向量   | 2    | [context/context-window.md](../../../projects/rag-knowledge-base/data/docs/context/context-window.md)   | 0.885303 |
| 向量   | 3    | [requests/finish-reason.md](../../../projects/rag-knowledge-base/data/docs/requests/finish-reason.md)   | 0.873025 |
| 向量   | 4    | [requests/retry-limit.md](../../../projects/rag-knowledge-base/data/docs/requests/retry-limit.md)       | 0.872654 |
| 向量   | 5    | [context/request-budget.md](../../../projects/rag-knowledge-base/data/docs/context/request-budget.md)   | 0.872427 |

两种方法的前两名仍然一致。`预算.md` 给出发送前检查长度的原则，`context/context-window.md` 说明一次请求应为活跃输入和计划输出分配容量。`context/request-budget.md` 则说明资料或历史变化后，要检查实际准备发送的最终请求，它在关键词结果中排第四，在向量结果中排第五。[最终请求预算检查原文](../../../projects/rag-knowledge-base/data/docs/context/request-budget.md)

关键词方法第三名的历史增长、第五名的历史裁剪也涉及输入长度变化和预算处理。向量方法第三、第四名分别讲结束原因和重试次数上限，与发送前的上下文长度检查关系较弱。本问题中，关键词方法后几名提供的资料更贴近检查目标。

## 任务 2 复现命令

以下命令均在配套项目目录执行，每种方法的一次调用包含同样的三个问题。

```shell
.venv/bin/python -m rag_knowledge_base data/docs --method keyword --k 5 \
  --query "请求一直没有返回怎么办？" \
  --query "怎样记录请求耗时？" \
  --query "发送前怎样检查上下文长度？"
```

模型已经缓存时，使用下面的命令复现向量试查。

```shell
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_knowledge_base data/docs --method vector --k 5 \
  --query "请求一直没有返回怎么办？" \
  --query "怎样记录请求耗时？" \
  --query "发送前怎样检查上下文长度？"
```

## 知识检查

题目见[本课知识检查](../embeddings-and-search.md#知识检查)。

### 文档准备和一次查询分别由应用完成哪些操作

文档准备发生在查询前，应用执行以下操作。

1. 读取文档，保留每篇文档的编号、标题、正文和来源。
2. 按选定模型的文档输入要求，将前缀、标题、换行和正文组成完整输入，用配套分词器检查长度。超过本课采用的限制时，报错并指出文档编号。
3. 调用 Embedding 模型为每篇文档生成向量，检查向量的维度和有效性，并核对向量条数与文档数。
4. 保存文档向量与文档编号的对应关系，供后续查询复用，并保留能够按编号取回的原文。

一次查询使用已经准备好的文档向量，应用执行以下操作。

1. 接收问题和 K，检查 K 是否为正整数。空白问题或空文档集合返回空结果。
2. 按模型的查询输入要求处理问题，调用 Embedding 模型生成问题向量，并检查向量的维度和有效性。
3. 将问题向量与每篇文档的向量交给余弦相似度公式计算，得到每篇文档的分数。
4. 按分数降序排列，同分时按文档编号升序排列，取前 K 篇或全部文档，再按编号取回文档记录，返回原文、来源等字段及分数。

文档内容和编码设置保持一致时，后续问题可以继续使用同一批文档向量，每次只为当前问题生成新向量。

### 为什么相同维度不足以保证向量兼容

维度相同说明两条向量包含相同数量的分量，余弦公式可以对它们逐项运算。检索还要求两侧向量来自配套的文本编码方式，计算所得分数才有依据用于估计问题与文档的相关程度。

两个不同模型都可以输出 384 维向量，但各自将文本转换为数值的方式可能不同。把一个模型的问题向量与另一个模型的文档向量放在一起，虽然可以算出余弦值，所得分数是否能反映文本相关性仍需要验证。

本课采用固定的兼容模型版本，分别按要求处理问题和文档的输入前缀，并配套使用相似度计算与归一化设置。更换为不兼容的模型版本后，应用需要重新生成文档向量，再与新模型生成的问题向量比较。

### 为什么没有答案的问题仍可能返回 Top-K 文档

本课的向量检索会给每篇文档计算分数，再按分数选出排在前面的文档。只要问题有效、语料非空且向量检查通过，就可以形成排名。即使所有原文都没有回答问题，程序仍会按本课的规则返回前 K 篇或全部文档。

Top-K 表示这批候选中的排名靠前者。某篇文档可能与问题主题相近，却缺少回答所需的具体事实。本课通过相似度排序选取候选文档，资料是否包含答案需要结合原文判断。
