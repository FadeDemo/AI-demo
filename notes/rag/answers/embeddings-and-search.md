---
title: Embedding 与逐篇检索练习记录
type: answer
area: rag
status: learning
created: 2026-11-10
updated: 2026-11-10
tags:
  - rag
  - embedding
  - semantic-search
  - answers
---

# Embedding 与逐篇检索练习记录

本文记录[Embedding 与逐篇检索](../embeddings-and-search.md)任务 1 的编码实现、离线测试和真实模型运行结果。配套代码位于 [RAG Knowledge Base 项目](../../../projects/rag-knowledge-base/README.md)。

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

默认套件发现 72 项测试，其中 71 项通过，1 项真实模型集成测试按默认设置跳过。编码组件的离线测试使用能记录调用的模型替身，替身同时提供编码结果、分词结果和声明的输出维度。

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
