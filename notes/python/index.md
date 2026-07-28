---
title: Python 工程基础
type: index
area: python
status: learning
created: 2026-07-21
updated: 2026-07-28
tags:
  - python
  - engineering
  - rag
---

# Python 工程基础

本专题补齐 RAG 入门所需的 Python 工程能力。学习目标不是记住所有 API，而是能够可靠地读取文档、让每个项目使用自己的一套第三方包，并让另一个人在新电脑上重新搭建出可用的项目环境。

## 建议学习顺序

1. [文件处理](file-handling.md)：读取目录中的文档，将不同文件转换为统一的数据结构。
2. [虚拟环境](virtual-environments.md)：理解项目为什么需要独立的 Python 和依赖环境。
3. [包管理](package-management.md)：把项目需要的第三方包写入配置，并完成安装、版本记录和更新。

三者在项目中的关系如下：

```text
创建独立环境 → 安装第三方包并记录版本 → 读取和处理知识库文件
```

## 练习回答

课程中的书面回答统一保存在[练习回答目录](answers/index.md)中，与概念讲解和可运行代码分开组织。

## 可运行示例

[Python 课程示例项目](../../projects/python/README.md) 提供与本专题配套的代码、测试和示例数据。下面以文件处理示例说明项目的运行和测试方式：

```shell
cd projects/python
uv sync
uv run python file_handling_demo.py
uv run python -m unittest discover -s tests -v
```

## 推荐练习项目

完成一个最小的“文档导入器”：

- 从指定目录及其子目录读取 `.txt`、`.md` 和 `.json` 文件。
- 将每个文件转换为包含正文 `content`、来源 `source` 和附加信息 `metadata` 的对象。
- 跳过不支持的文件，并为读取失败输出可定位的错误信息。
- 使用 `uv` 管理 Python 版本和第三方依赖。
- 在 README 中写清楚从克隆仓库到运行程序的命令。

## 完成标准

- 能解释工作目录与文件路径的区别。
- 能使用 `with` 语句读写文件，并确保使用完毕后文件会被关闭。
- 能说明虚拟环境解决了什么问题。
- 能区分“在代码中导入包”“把包装进环境”和“把需要的包写入项目配置”。
- 删除本地虚拟环境后，仍能根据项目文件恢复相同环境。

完成本专题后，可以回到[人工智能学习路线](../roadmap.md)，继续第 1 阶段的 LLM 应用基础。
