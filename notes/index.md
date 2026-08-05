---
title: AI 学习笔记
type: index
area: ai
status: active
created: 2026-07-20
updated: 2026-08-05
tags:
  - ai
  - index
---

# AI 学习笔记

这里是学习知识库的总入口。该目录只使用通用 Markdown，可以直接用 Obsidian、Joplin、Typora、VS Code 或其他 Markdown 工具阅读和维护。

## 从这里开始

- [人工智能学习路线](roadmap.md)：以 RAG 为短期目标，逐步进入 LLM、Agent 开发和 AI Infra。
- [Python 工程基础](python/index.md)：学习文件处理、虚拟环境和包管理，补齐 RAG 的编程前置。
- [通用工程基础](engineering/index.md)：学习日志与基础测试，让程序的问题可定位、修改可验证。
- [LLM 使用基础](llm/index.md)：学习消息、上下文、生成参数、Prompt、结构化输出、工具调用、可靠性、安全和评测。
- [代码项目目录](../projects/README.md)：查看与学习路线配套的实践项目。

## 当前学习重点

短期主线是完成一个可评测、可部署、带引用的 RAG 项目。具体前置知识、8 周安排、验收标准和面试知识点统一维护在 [Roadmap](roadmap.md) 中。

## 后续扩展规则

只有在某个主题产生独立内容时才创建对应目录，避免提前制造空笔记。建议按领域逐步扩展：

```text
notes/
├── python/                 # 文件处理、虚拟环境与包管理
├── engineering/            # 日志、测试与通用工程实践
├── rag/                    # 检索、切块、评测、生产化
├── llm/                    # 模型原理、PyTorch、微调与推理
├── agents/                 # Tool Calling、工作流、MCP 与安全
├── ai-infra/               # Linux、Docker、GPU、vLLM、Kubernetes
├── experiments/            # 可复现的学习实验和结果
├── resources/              # 已筛选的课程、论文和官方文档
└── assets/                 # 笔记引用的图片和图表
```

每个领域目录使用自己的 `index.md` 作为入口。路线图只维护学习顺序和验收标准，详细原理逐步迁移到对应主题笔记。

## 笔记元数据

新增笔记时建议使用以下最小格式：

```yaml
---
title: 笔记标题
type: concept
area: rag
status: learning
created: 2026-07-20
updated: 2026-07-20
tags:
  - ai
---
```

建议的 `type`：`index`、`roadmap`、`concept`、`experiment`、`project`、`resource`。建议的 `status`：`planned`、`learning`、`completed`、`evergreen`。
