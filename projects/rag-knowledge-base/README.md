# RAG Knowledge Base

本项目配套 [RAG 检索基础](../../notes/rag/index.md)，后续按课程顺序实现文档读取、关键词检索、向量检索与评测。

当前已实现文档记录、单文件读取和目录批量读取，并使用独立虚拟环境。命令行入口可以显示载入数量和文档编号，也可以按编号展示标题、来源和原文。任务 1 的练习语料共 50 篇。

## 代码组织

项目自己的 Python 包名为 `rag_knowledge_base`，放在 `src/` 中。安装后，程序入口和测试都通过包名导入代码。

```text
rag-knowledge-base/
├── pyproject.toml
├── uv.lock
├── .python-version
├── src/
│   └── rag_knowledge_base/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── document.py
│       └── document_loader.py
├── data/
│   ├── README.md
│   └── docs/
│       ├── context/
│       ├── engineering/
│       ├── output/
│       ├── python/
│       ├── requests/
│       ├── 日志.md
│       ├── 超时.md
│       └── 预算.md
├── tests/
└── main.py
```

`cli.py` 负责参数解析、文档列表和按编号查看。`document.py` 定义文档记录类型，`document_loader.py` 提供单文件和目录读取函数。`__init__.py` 标记 Python 包，`__main__.py` 支持通过模块名运行。根目录的 `main.py` 转调同一个入口。

练习文档放在 `data/docs/`，出处和使用范围记录在[语料说明](data/README.md)，测试放在 `tests/`。

## 环境与运行

项目使用 Python 3.13 和 uv，目前没有第三方运行依赖。打包工具使用与第一阶段相同的 `uv_build`，由 uv 在同步环境时处理。在项目目录中执行以下命令。

```shell
uv sync --locked
uv run rag-knowledge-base data/docs
```

运行后应显示 `载入 50 个文档`，随后逐行列出编号。`data/docs` 是必填的语料根目录参数，相对路径以运行命令时所在的目录为起点。

`pyproject.toml` 声明项目信息与依赖，`uv.lock` 保存解析结果，`.python-version` 记录 Python 版本选择，`.venv/` 保存本地虚拟环境。

下面两种形式也会调用同一个入口。

```shell
uv run python -m rag_knowledge_base data/docs
uv run python main.py data/docs
```

查看指定文档时，同时提供语料根目录和完整编号。子目录中的编号使用 `/` 分隔，并保留文件扩展名。

```shell
uv run rag-knowledge-base data/docs --doc-id 超时.md
uv run rag-knowledge-base data/docs --doc-id requests/retry-limit.md
uv run rag-knowledge-base --help
```

`--doc-id` 为可选参数。提供它时，入口只展示对应文档的编号、标题、正文和来源。编号不存在时，错误信息写入标准错误输出，进程以状态码 2 退出。

## 开始第一课

课程给定的三个样本文档保存在 `data/docs/` 根目录，编号分别为 `超时.md`、`日志.md`、`预算.md`。各文件采用课程中的例句，并添加同名一级标题。另有 47 篇依据仓库课程改写的短文，按主题放在五个子目录中。全部文档采用 UTF-8 Markdown 格式，每篇围绕一个较小主题。

按[文档与关键词检索](../../notes/rag/retrieval-and-documents.md)任务 1，文档记录包含 `doc_id`、`title`、`text`、`source` 四个字符串字段。

`load_documents` 接收语料根目录，读取该目录及其各级子目录中的 `.txt`、`.md` 文件，扩展名匹配不区分大小写。编号和来源都采用相对于语料根目录的路径，标题取文件名去掉扩展名的部分。例如，`requests/retry-limit.md` 的标题为 `retry-limit`，原文中的中文 Markdown 标题作为正文保留。

正文按 UTF-8 读取，统一换行并清除首尾空白。空文件和只有空白的文件会被跳过，日志记录文件路径与原因。根目录不存在、根目录指向文件、文件读取失败或 UTF-8 解码失败时，异常向上传递，命令以非零状态退出。

在项目目录运行 `uv run python` 后，可以直接调用目录读取函数。

```python
from pathlib import Path
from rag_knowledge_base.document_loader import load_documents

documents = load_documents(Path("data/docs"))
print(len(documents))
print([document.doc_id for document in documents])
```

当前完整语料应返回 50 条文档记录。编号由相对路径生成，返回列表按文件遍历次序排列。

测试使用 Python 标准库 `unittest`，在项目目录执行以下命令。

```shell
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

当前共有 21 项测试，覆盖单文件和目录读取、正文清理、子目录遍历、文件筛选、编号稳定性、空文件日志，以及读取和解码失败。命令行测试从模块入口启动子进程，验证列表、按编号查看、帮助信息和失败退出。测试自行构造练习文件。

## 任务 1 验收记录

2026-11-04 完成以下核对。

- 使用 `uv run --offline --no-sync rag-knowledge-base data/docs` 实际载入 50 篇文档，列出的编号与语料文件逐一对应。
- 重复读取完整语料，两次结果的编号、标题、正文和来源一致，50 篇正文均非空且各不相同。
- 从命令行逐个查询全部 50 个编号，展示的标题、来源和正文均与文件一致。模块入口和根目录脚本入口也能载入完整语料。
- 21 项自动化测试全部通过。小目录测试覆盖增加文件后已有记录保持一致、空文件跳过与原因日志，以及读取和解码失败。命令行测试覆盖按编号查看和失败退出。
- 原有三个手算样本保留，新增短文的出处与练习使用范围记录在[语料说明](data/README.md)。

## 切换编辑器环境

在仓库根目录运行下面的命令，让共享配置及正在运行的 VS Code、Cursor 使用本项目的解释器。

```shell
use-venv projects/rag-knowledge-base --editor both
```

已有终端继续保留原来的环境。切换完成后新建终端，再用 `python -c "import sys; print(sys.executable)"` 核对解释器路径。
