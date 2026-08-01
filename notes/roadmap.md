---
title: 人工智能学习路线
type: roadmap
area: ai
status: active
created: 2026-07-20
updated: 2026-08-01
tags:
  - ai
  - rag
  - llm
  - agents
  - ai-infra
---

[返回学习笔记首页](index.md)

# 人工智能学习路线：以 RAG 为短期目标，走向 LLM、AI Infra 与 Agent 开发

> 版本：2026-07-20
>
> 默认投入：每周 10～12 小时
>
> 默认起点：会一点编程，但没有系统学习过机器学习或 LLM

## 1. 先回答最重要的问题：学 RAG 需要前置知识吗？

需要，但没有想象中那么多。

你**不需要**先完成高等数学、机器学习、深度学习、PyTorch 和 Transformer 全套课程，才有资格开始 RAG。RAG 首先是一类 AI 应用工程：系统先从外部知识库检索相关内容，再把内容和问题一起交给 LLM 生成答案。它涉及 LLM，但大量工作其实属于后端开发、数据处理、搜索和系统评测。

### 开始 RAG 前必须具备

- Python 基础：函数、类、异常、[文件处理](python/file-handling.md)、[虚拟环境](python/virtual-environments.md)、[包管理](python/package-management.md)。
- 工程基础：Git、命令行、[日志](engineering/logging.md)、环境变量、[基础测试](engineering/basic-testing.md)。
- Web 基础：HTTP、REST API、JSON、同步与异步的基本区别。
- LLM 使用基础：消息角色、Prompt、Token、上下文窗口、温度、结构化输出。
- 数据基础：能处理 TXT、Markdown、PDF 解析结果和简单表格数据。

### 可以在做 RAG 的过程中学习

- Embedding、向量、余弦相似度。
- Top-K 检索、召回率、准确率、BM25、混合检索。
- Chunk、Metadata、向量数据库、Reranker。
- RAG 的离线评测、线上观测、延迟与成本。

### 暂时不必作为前置条件

- 从零训练神经网络或 LLM。
- 完整推导反向传播和 Transformer 数学公式。
- CUDA Kernel、分布式训练、Kubernetes。
- 微调、LoRA、RLHF。

这些内容对长期学习 LLM 和 AI Infra 很重要，但不是做出第一个可靠 RAG 的门票。

---

## 2. 总体路线图

```text
Python 与后端基础
        ↓
LLM API 与核心概念
        ↓
Embedding + 信息检索基础
        ↓
Naive RAG → 可评测 RAG → Production RAG
        ↓                         ↓
Agent 开发                  AI Infra / 推理服务
        ↓                         ↓
工具调用、工作流、MCP      Docker、GPU、vLLM、K8s
        └──────────┬──────────────┘
                   ↓
          可靠的 AI 系统工程能力
```

建议采用“一条主线、两条支线”：

- 主线：先用 8 周做出一个可评测、可部署的 RAG 项目。
- 支线 A：补 LLM、Transformer、PyTorch 原理。
- 支线 B：补 Linux、网络、容器、服务治理和 GPU 推理。

不要同时追逐多个 Agent/RAG 框架。面试和工作最终考察的是你是否理解数据流、失败原因、指标和取舍，而不是记住某个框架的 API。

---

## 3. 第 0 阶段：编程与工程基础自检（0～2 周，按需）

如果下面任务能独立完成，可以直接进入第 1 阶段：

- 用 Python 读取一个目录下的 Markdown 文件并转成对象列表。
- 调用一个 HTTP API，正确处理超时、重试和异常状态码。
- 用 FastAPI 写两个接口，并用 `curl` 或 API 客户端测试。
- 使用 Git 创建分支、提交代码、查看 diff。
- 使用 `pytest` 给一个文本处理函数写 3 个测试。
- 知道密钥为什么应放在环境变量中，且不能提交进仓库。

### 学习内容

- Python：数据结构、类型标注、生成器、上下文管理器、异步基础。
- 工程：Git、Linux 常用命令、[日志](engineering/logging.md)、[基础测试](engineering/basic-testing.md)、依赖管理。
- 后端：HTTP、JSON、REST、FastAPI、SQLite/PostgreSQL 基础。

### 阶段产物

做一个“文档搜索 API”：导入本地 Markdown，使用普通关键词匹配返回结果。此时先不接 LLM，也不需要向量数据库。

### 通过标准

- 项目可通过 README 在另一台机器上复现。
- API 输入、输出有明确的数据结构。
- 错误不会只打印一句 `something went wrong`，而是有可定位的日志。

---

## 4. 第 1 阶段：LLM 应用基础（第 1 周）

### 必学概念

- Token 与 tokenizer：文字如何变成模型处理的序列。
- 上下文窗口：Prompt、历史消息、检索材料和输出都占用上下文。
- 消息角色：system、user、assistant、tool。
- 生成参数：temperature、top-p、max tokens；知道它们不能修复知识缺失。
- Structured Output：让模型按 JSON Schema 返回结果。
- Tool/Function Calling：模型选择工具，应用程序负责真实执行。
- Streaming、超时、重试、速率限制、并发与幂等性。
- Prompt Injection 与数据泄露的基本风险。

### 动手任务

只使用模型 SDK，不使用 LangChain/LlamaIndex：

1. 写一个终端聊天程序。
2. 加入流式输出。
3. 加入结构化 JSON 输出。
4. 记录每次请求的延迟、输入/输出 Token 和估算成本。
5. 为 API 超时和限流实现有限次数的指数退避重试。

### 你应该能解释

- 为什么 temperature 不是“事实正确度旋钮”？
- 为什么上下文更长不等于答案一定更好？
- 模型 SDK 返回 429、超时和格式不合法时分别如何处理？
- Function Calling 与直接让模型输出一段 JSON 有何区别？

---

## 5. 第 2 阶段：RAG 的最小理论前置（第 2 周）

### 5.1 Embedding 与向量检索

先达到“会用、会解释”，再追求数学推导：

- Embedding 把文本映射成稠密向量，语义相近的文本通常距离更近。
- 理解向量维度、归一化、余弦相似度、点积和欧氏距离。
- Query 和 Document 必须使用兼容的 Embedding 模型与输入方式。
- 向量数据库不是魔法，本质是向量、元数据、索引和查询能力的组合。
- ANN 是近似最近邻检索；理解 HNSW 在召回、延迟、内存间的取舍即可。

只需先掌握一个公式的含义：

```text
cosine_similarity(a, b) = (a · b) / (||a|| × ||b||)
```

### 5.2 信息检索基础

这是 RAG 面试中非常容易被忽略、但比“会调框架”更重要的部分：

- 词法检索：倒排索引、TF-IDF 的直觉、BM25 的直觉。
- 语义检索：Dense Embedding + ANN。
- Top-K：候选取少了会漏召回，取多了会增加噪声和上下文成本。
- Precision 与 Recall：RAG 第一阶段通常更看重召回，后续用 rerank 提升精度。
- Hybrid Search：结合关键词的精确匹配与向量的语义匹配。
- Reranking：用更贵的模型对较小的候选集重新排序。

### 动手任务

用 50～100 篇小文档做一个检索实验：

1. 实现简单关键词检索。
2. 实现 Embedding 暴力检索；数据少时先用 NumPy 即可。
3. 为 20 个问题人工标注相关文档。
4. 对比两种检索的 Recall@K、MRR 和失败案例。

完成这个实验后再引入向量数据库。这样你会理解数据库替你做了什么。

---

## 6. 第 3 阶段：8 周 RAG 实战主线

目标项目建议：**带引用的中文技术文档知识库**。数据可以使用某个开源项目的官方文档、课程笔记或你熟悉领域的公开资料。不要一开始就使用充满复杂表格和扫描图片的 PDF。

### 第 1 周：LLM API 基础

- 完成第 4 节的终端应用。
- 学会 Token 预算、结构化输出、错误处理和成本记录。
- 建立最小测试集，不依赖“我看起来觉得回答不错”。

产物：`chat_cli` 和至少 10 个自动化测试用例。

### 第 2 周：从零实现最小检索器

- 文档清洗与规范化。
- 固定长度切块，并保存 `source`、`title`、`section`、`chunk_id`。
- 生成 Embedding。
- 用 NumPy 计算相似度并取 Top-K。

产物：输入问题后，返回 Top-K 文本块和相似度，不生成答案。

### 第 3 周：完成 Naive RAG

- 将检索结果组装进 Prompt。
- 要求模型仅依据上下文回答；依据不足时明确拒答。
- 输出答案、引用来源和检索到的原文片段。
- 使用 FastAPI 暴露 `/ingest`、`/retrieve`、`/answer` 接口。

产物：第一个端到端 RAG，但暂时不要宣称“生产可用”。

### 第 4 周：数据摄取与 Chunk 优化

- 对比固定长度、按标题/段落、递归切分。
- 理解 chunk size 与 overlap 对召回、噪声和成本的影响。
- 保留父子结构和完整 Metadata。
- 处理增量更新、重复文档、删除和版本号。
- 学习 PDF 常见问题：页眉页脚、乱码、多栏、表格、OCR。

产物：一份 chunk 策略实验报告，不能只写“500 tokens 效果最好”，要说明数据与指标。

### 第 5 周：向量数据库与混合检索

- 选择一个：Qdrant 或 PostgreSQL + pgvector。
- 学会 collection/table schema、payload/metadata filter、索引和批量写入。
- 加入 BM25/稀疏检索，与 Dense Retrieval 做混合检索。
- 使用 RRF 等方法融合多个排名。

产物：可切换 dense、sparse、hybrid 三种检索模式，并对比指标。

### 第 6 周：Rerank、Query 改写与路由

- 在初检 Top-20/50 后，用 reranker 选出 Top-5/8。
- 对多轮对话先生成独立检索问题，避免直接拿完整聊天历史检索。
- 尝试 Multi-query，但必须评估它带来的延迟和成本。
- 对无需知识库的问题、越权问题和不支持的问题进行路由或拒答。

产物：展示 rerank 前后的 Recall@K、MRR/NDCG、延迟和成本变化。

### 第 7 周：建立 RAG 评测体系

至少建立 50～100 条评测集，覆盖：

- 普通事实问题。
- 同义表达和模糊问题。
- 关键词/编号类问题。
- 跨文档问题。
- 无答案问题。
- 过时、冲突和权限受限内容。
- Prompt Injection 样例。

把系统拆开评估：

| 层次 | 核心问题                   | 建议指标                                          |
| ---- | -------------------------- | ------------------------------------------------- |
| 摄取 | 文档是否被正确解析和切块？ | 解析成功率、重复率、人工抽查                      |
| 检索 | 正确证据是否进入候选集？   | Recall@K、Precision@K、MRR、NDCG                  |
| 生成 | 回答是否由证据支持？       | Faithfulness/Groundedness、答案相关性、引用正确率 |
| 系统 | 用户是否能稳定使用？       | P50/P95 延迟、错误率、Token/请求、单次成本        |

LLM-as-a-Judge 可以辅助评测，但不能当唯一真相。对核心测试集保留人工标注，并定期检查评审模型的偏差。

产物：一个可重复运行的 eval 命令，能输出当前版本与基线的对比结果。

### 第 8 周：部署、可观测性与安全

- 使用 Docker Compose 启动 API、数据库/向量库和必要服务。
- 加入 request ID、结构化日志、trace、延迟和 Token 统计。
- 为摄取和查询实现超时、重试、并发限制和缓存策略。
- 区分文档权限，在检索阶段做 Metadata/ACL 过滤。
- 防御 Prompt Injection：外部文档是数据，不是可信指令。
- 敏感信息不进入日志、Prompt 和公开评测集。
- 写清楚故障降级：检索失败、模型失败、reranker 超时分别怎么办。

产物：一个可部署项目、架构图、评测报告和 3～5 分钟演示视频。

---

## 7. RAG 项目的推荐技术栈

技术栈的重点是“少而完整”，不是把所有流行名词放进简历。

| 层次       | 第一版推荐                                       | 学习目的                     |
| ---------- | ------------------------------------------------ | ---------------------------- |
| 语言       | Python 3.11+                                     | AI 生态与后端开发            |
| API        | FastAPI + Pydantic                               | 接口、校验、异步基础         |
| LLM        | 任一可靠模型 API                                 | 先掌握通用消息和工具调用语义 |
| Embedding  | 一种中英文效果可靠的模型                         | 建立固定基线，避免频繁换模型 |
| 本地检索   | NumPy/FAISS（二选一）                            | 理解向量检索本质             |
| 向量存储   | Qdrant 或 pgvector（二选一）                     | 索引、过滤、持久化、运维     |
| 关键词检索 | Elasticsearch/OpenSearch，或数据库支持的全文检索 | BM25 与混合检索              |
| Reranker   | 一个 cross-encoder/rerank API                    | 两阶段检索                   |
| 评测       | 自建 pytest + 指标脚本，可辅以 Ragas             | 保证变更可比较               |
| 服务       | Docker Compose                                   | 可复现部署                   |
| 可观测性   | OpenTelemetry 思路 + 结构化日志                  | 定位检索、模型和系统问题     |

框架选择建议：

1. 第一版尽量直接使用模型 SDK、数据库 SDK 和 Python 函数。
2. 明白完整数据流后，再选 LangChain、LlamaIndex 或其他一个框架。
3. 面试时能脱离框架画出 ingestion 与 query 两条链路。

---

## 8. RAG 面试知识地图

### 高频概念题

- RAG 与微调分别解决什么问题？什么时候组合使用？
- 为什么 RAG 仍会产生幻觉？
- 文档应如何切块？chunk size 和 overlap 如何通过实验确定？
- Embedding 模型如何选择？更换模型后为什么通常要重建索引？
- 余弦相似度、点积、欧氏距离有什么关系？归一化会带来什么影响？
- BM25 与向量检索各自擅长什么？为什么要做 Hybrid Search？
- HNSW 是什么？`efSearch`/类似搜索参数如何影响召回和延迟？
- Metadata Filter 应在检索前还是检索后？权限过滤为什么不能只依赖 Prompt？
- Reranker 为什么通常放在初检之后？候选数如何选择？
- 如何评估检索和生成？为什么只评最终答案无法定位问题？
- 如何处理多轮对话中的指代、省略和话题切换？
- 如何处理知识更新、删除、重复、冲突和时效性？
- 如何防止文档中的 Prompt Injection？
- 长上下文模型出现后，RAG 是否还有价值？
- 如何优化 P95 延迟、吞吐量和单次成本？

### 高频系统设计题

题目示例：为 100 万份企业文档设计多租户 RAG。

回答时依次覆盖：

1. 需求与 SLO：数据量、QPS、更新频率、语言、延迟、正确率、成本。
2. 摄取链路：解析、清洗、切块、去重、Embedding、版本和失败重试。
3. 存储设计：原文、Metadata、向量、关键词索引的职责划分。
4. 查询链路：改写、过滤、混合检索、融合、rerank、生成和引用。
5. 权限与安全：租户隔离、ACL、密钥、审计、注入攻击、PII。
6. 评测与观测：离线数据集、线上指标、trace、回归和灰度。
7. 扩展与降级：分片、缓存、批处理、限流、模型/检索故障策略。

### 项目描述应该包含的数字

简历不要只写“基于某框架搭建 RAG”。至少写出：

- 文档量和评测集规模。
- 基线与优化后的 Recall@K/MRR/引用正确率。
- P50/P95 延迟。
- 单次平均 Token 或成本。
- 优化前后的具体变化与取舍。

---

## 9. 长期路线 A：LLM 原理与模型能力（第 3～8 个月）

RAG 项目完成后，再系统补模型原理，此时抽象概念会有实际落点。

### A1. 数学与机器学习基础（4～6 周）

- 线性代数：向量、矩阵乘法、范数、特征值直觉。
- 微积分：导数、偏导、链式法则、梯度。
- 概率统计：条件概率、期望、方差、常见分布、最大似然。
- 机器学习：训练/验证/测试集、过拟合、损失函数、正则化、优化器。

目标不是做题竞赛，而是能看懂 loss、gradient、softmax、cross entropy 和 embedding。

### A2. PyTorch 与深度学习（4～6 周）

- Tensor、Dataset/DataLoader、Autograd、Module、训练循环。
- MLP、Embedding、Attention 的小规模实现。
- GPU、batch、混合精度、checkpoint 的基本概念。

项目：不用高级 Transformer 封装，写一个小型文本分类模型，再实现单头 self-attention。

### A3. Transformer 与 LLM（6～8 周）

- Tokenization：BPE/WordPiece/Unigram 的直觉。
- Self-Attention、Multi-Head Attention、位置编码、残差和归一化。
- Decoder-only 模型与 next-token prediction。
- Pretraining、SFT、LoRA/PEFT、Preference Optimization 的目标差异。
- 推理：prefill/decode、KV Cache、sampling、量化、batching。

项目：

- 阅读并运行一个最小 GPT 实现。
- 对小模型做一次 LoRA 微调并设计严格对照实验。
- 比较 Prompt、RAG、微调分别适合哪些知识与行为问题。

---

## 10. 长期路线 B：Agent 开发（第 3～6 个月）

Agent 不是“把 RAG 套进更复杂的框架”，而是模型在一个受控循环中观察状态、选择工具、执行动作并根据结果继续决策。

### B1. 先实现单 Agent 循环

不用框架实现：

```text
用户目标 → 模型决策 → 校验工具参数 → 执行工具
        ↑                              ↓
        └────── 工具结果 / 状态更新 ────┘
```

必学：

- Tool schema 与参数校验。
- 状态、短期记忆、长期记忆的区别。
- 最大步数、超时、预算和终止条件。
- 可重试错误与不可重试错误。
- 幂等性、审批点和副作用控制。
- 工具权限、沙箱、审计日志。
- Agent eval：任务成功率、工具选择正确率、步骤数、成本和延迟。

### B2. 再学习工作流编排

- 确定性工作流与自主 Agent 的边界。
- Router、Planner-Executor、ReAct、并行分支、人工审批。
- Checkpoint、暂停/恢复、长任务和队列。
- 多 Agent 只在角色/权限/上下文边界确实独立时使用，不要为了概念新而拆分。

### B3. 学习 MCP 与外部系统集成

- 理解 Host、Client、Server。
- 理解 Tools、Resources、Prompts。
- 实现一个只读 MCP Server，例如查询自己的知识库。
- 再实现有副作用的工具，并加入身份认证、授权和人工确认。

### Agent 项目建议

做一个“代码仓库维护助手”：

- 检索仓库文档和历史问题。
- 调用只读代码搜索、测试和静态检查工具。
- 生成执行计划。
- 对写文件、发消息或部署等副作用操作设置人工审批。
- 用固定任务集评估成功率，而不是只录一次成功演示。

---

## 11. 长期路线 C：AI Infra（第 4～12 个月）

AI Infra 范围很大，建议分为“通用基础设施 → 推理服务 → 训练/数据基础设施”，不要直接从 CUDA 或 Kubernetes 开始。

### C1. 通用系统基础（4～8 周）

- Linux：进程、线程、内存、文件系统、权限、信号。
- 网络：TCP、HTTP、DNS、TLS、负载均衡、连接池。
- 数据库：索引、事务、隔离级别、复制、分片的直觉。
- 并发：线程、进程、async IO、队列、背压。
- 可观测性：log、metric、trace、SLO、P50/P95/P99。
- Docker：镜像、容器、网络、volume、Compose。

项目：把 RAG 拆成 API、worker、向量库，用队列执行文档摄取，并补齐监控与故障重试。

### C2. LLM 推理基础设施（6～10 周）

- GPU 基础：显存、带宽、计算吞吐、CPU-GPU 数据移动。
- 模型内存估算：参数、KV Cache、激活值。
- Prefill 与 Decode 的不同计算特征。
- Continuous Batching、Paged Attention、Prefix Caching。
- Tensor/Pipeline/Data Parallel 的用途与边界。
- FP16/BF16/INT8/INT4 量化的效果、速度和精度取舍。
- vLLM 等推理引擎的服务、批处理和指标。
- 吞吐、首 Token 延迟（TTFT）、每 Token 延迟（TPOT）、尾延迟。

项目：用同一模型比较不同 batch、上下文长度、量化配置的 TTFT、TPOT、吞吐和显存。

### C3. 云原生与集群（6～10 周）

- Kubernetes：Pod、Deployment、Service、ConfigMap、Secret、HPA。
- GPU 调度、节点选择、资源配额、滚动更新。
- 模型权重分发、缓存、冷启动、自动扩缩容。
- 灰度发布、回滚、容量规划与成本治理。

只有当单机 Docker 服务已经熟悉后再进入这一层。

### C4. 训练与数据基础设施（进阶）

- 数据采集、清洗、去重、版本管理与 lineage。
- 分布式训练：DDP、FSDP/ZeRO 的目标和通信开销。
- Checkpoint、断点恢复、容错和实验追踪。
- 数据并行、张量并行、流水线并行的取舍。
- 调度、集群利用率、网络拓扑和存储吞吐。

---

## 12. 一年学习节奏建议

| 时间         | 主线                               | 可展示成果                         |
| ------------ | ---------------------------------- | ---------------------------------- |
| 第 1～2 月   | RAG 必要前置 + 8 周项目            | 带引用、评测、部署的 RAG           |
| 第 3～4 月   | 数学/ML/PyTorch + Agent 基础       | 小模型训练实验 + 单 Agent 工具循环 |
| 第 5～6 月   | Transformer/LLM + Agent 工作流/MCP | LoRA 对照实验 + 带权限的 Agent     |
| 第 7～9 月   | Linux/网络/Docker + LLM 推理       | vLLM 服务与性能基准报告            |
| 第 10～12 月 | Kubernetes/分布式/系统设计         | 可扩展 AI 服务架构与压测报告       |

每周 10～12 小时可以这样分配：

- 60%：写代码和做项目。
- 20%：原理课程、官方文档和论文。
- 10%：评测、复盘和技术文章。
- 10%：面试题与系统设计表达。

每两周必须产出一个可验证结果：代码、测试、指标、实验报告或演示。不要把“看完课程”当成完成标准。

---

## 13. 如何判断自己已经达到不同水平

### RAG 入门完成

- 能从零画出 ingestion 与 query 两条链路。
- 能不用框架实现一个最小 RAG。
- 能解释一次坏答案究竟是解析、检索、排序还是生成的问题。
- 有固定评测集，优化前后有数字对比。

### LLM 应用开发合格

- 能处理结构化输出、工具调用、流式响应、重试和限流。
- 能控制 Token、延迟、成本、安全边界和可观测性。
- 能区分 Prompt、RAG、微调和 Agent 的适用场景。

### Agent 开发合格

- 能实现有终止条件和错误恢复的工具循环。
- 对副作用操作有授权、审批、幂等和审计设计。
- 能用任务集评估成功率，而不是依赖演示效果。

### AI Infra 入门完成

- 能解释模型服务的 TTFT、TPOT、吞吐和显存瓶颈。
- 能用 Docker 部署并观测服务。
- 能进行基准测试、容量估算和基本故障定位。

---

## 14. 推荐资料（优先官方与原始论文）

### RAG 与检索

- [RAG 原始论文：Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- [Qdrant：Hybrid and Multi-Stage Queries](https://qdrant.tech/documentation/search/hybrid-queries/)
- [Qdrant：Hybrid Search with Reranking](https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/)
- [Ragas：RAG 与 Agent 评测指标](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)

### LLM 与 PyTorch

- [Hugging Face LLM Course](https://huggingface.co/learn/llm-course/en/chapter1/1)
- [Hugging Face Tokenization Algorithms](https://huggingface.co/docs/transformers/main/tokenizer_summary)
- [PyTorch Learn the Basics](https://docs.pytorch.org/tutorials/beginner/basics/intro)

### Agent 与协议

- [Model Context Protocol：Architecture Overview](https://modelcontextprotocol.io/docs/learn/architecture)

### AI Infra

- [Docker Get Started](https://docs.docker.com/get-started/)
- [Kubernetes Concepts](https://kubernetes.io/docs/concepts/)
- [vLLM Documentation](https://docs.vllm.ai/en/latest/)

资料使用原则：官方文档解决“现在怎样正确使用”，论文解决“方法为什么出现”，项目实验解决“在你的数据上是否真的有效”。
