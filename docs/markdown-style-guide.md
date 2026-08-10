# Markdown 规范

本规范适用于仓库中的所有 Markdown 文件。目标是在 Obsidian、Joplin、Typora、VS Code、GitHub 和普通文本编辑器之间保持可读、可格式化和可迁移。

## 工具和命令

仓库使用 Prettier 进行格式化，使用 markdownlint-cli2 进行 Lint。首次使用时安装仓库声明的开发依赖：

```shell
npm install
```

这些是仓库级的 Markdown 质量工具，不代表代码项目必须采用 Node.js。依赖会安装在仓库本地的 `node_modules/`，不要求全局安装 Prettier 或 markdownlint-cli2。未来若引入 Python 工具，则使用 `uv` 声明、锁定和运行，不使用未记录的全局 Python 包。

常用命令：

```shell
# 格式化所有 Markdown 文件
npm run format

# 仅检查格式，不修改文件
npm run format:check

# 检查 Markdown 结构与风格
npm run lint
```

提交 Markdown 变更前，必须依次运行：

```shell
npm run format
npm run lint
```

格式化可能修改文件，因此需要在 Lint 前执行并重新检查变更。

## 文件组织

- 笔记保存在 `notes/`，可运行代码保存在 `projects/`。
- 每个目录使用 `index.md` 或 `README.md` 作为入口。
- 普通 Markdown 文件使用小写 kebab-case，例如 `rag-evaluation.md`。
- `README.md` 和 `index.md` 是入口文件的命名例外。
- 图片和笔记附件保存在对应知识库的 `assets/` 中。

## 标题

- 每个文件只使用一个一级标题。
- 标题层级逐级递进，不从二级标题直接跳到四级标题。
- 标题前后保留空行。
- 标题表达内容主题，不使用“其他”“补充”等缺乏上下文的名称。

## 段落和列表

- 段落之间保留一个空行。
- 无序列表统一使用 `-`。
- 列表标记之后保留一个空格。
- 不使用空格手工对齐普通段落。
- 中文长段落不强制按固定列宽换行，避免产生不必要的 diff。

## 代码、表格和引用

- 代码块使用三个反引号，并尽可能声明语言，例如 `python`、`shell`、`json` 或 `text`。
- 行内命令、文件名、配置键和代码标识符使用反引号。
- 表格必须包含表头和分隔行。
- 引用内容使用 `>`，不要使用缩进模拟引用。
- 示例中的密钥、Token、地址和个人信息必须使用明显的占位符。

## 链接和附件

- 内部链接使用标准 Markdown 相对链接，例如 `[RAG 评测](rag/evaluation.md)`。
- 不使用绝对文件路径、`file://` URL 或依赖特定笔记软件的 URI。
- 核心导航不使用 Wikilink、块引用或插件查询。
- 外部链接使用有含义的标题，不使用裸 URL 充当正文。
- 图片使用相对路径，并提供能够说明内容的替代文本。

## YAML Front Matter

学习笔记可以使用简单 YAML 元数据：

```yaml
---
title: RAG 评测
type: concept
area: rag
status: learning
created: 2026-07-20
updated: 2026-07-20
tags:
  - ai
  - rag
---
```

- 只使用字符串、布尔值、日期、数字和简单列表。
- 不使用嵌套对象或某个插件专用的数据结构。
- `updated` 在笔记内容发生实质变化时更新。
- YAML 元数据不能代替正文标题。

`status` 表示学习者的进度，不表示课程文档是否已经写完：

- `planned`：课程、概念笔记或实验已经规划，但学习者尚未开始。
- `learning`：学习者正在阅读或继续学习材料，或者正在回答课程问题、实现或调试练习、请求课程任务的阶段验收。
- `completed`：学习者明确确认已经完成该材料的学习与必修验收。

仅要求创建、改写或润色供以后使用的课程内容，不算已经开始学习；应通过 `updated` 记录内容修订，不因文档完整而改变学习进度。

## 规则例外

仓库关闭 Markdown 行长规则，因为中文内容和长链接不适合机械断行。不同父级章节允许使用相同的小标题；同一章节内仍不允许重复标题。其他规则如需调整，应修改 `.markdownlint-cli2.jsonc` 并在本文件中说明原因，不在单个文件中静默绕过。
