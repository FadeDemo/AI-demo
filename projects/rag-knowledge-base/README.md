# RAG Knowledge Base

本项目配套 [RAG 检索基础](../../notes/rag/index.md)，后续按课程顺序实现文档读取、关键词检索、向量检索与评测。

当前已实现文档记录、单文件读取和目录批量读取，并使用独立虚拟环境。命令行入口目前仍输出项目就绪提示。

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
│   └── docs/
├── tests/
└── main.py
```

`cli.py` 负责命令行入口，目前保留就绪提示。`document.py` 定义文档记录类型，`document_loader.py` 提供单文件和目录读取函数。`__init__.py` 标记 Python 包，`__main__.py` 支持通过模块名运行。根目录的 `main.py` 转调同一个入口，保留原有启动命令。

样本文档放在 `data/docs/`，测试放在 `tests/`。

## 环境与运行

项目使用 Python 3.13 和 uv，目前没有第三方运行依赖。打包工具使用与第一阶段相同的 `uv_build`，由 uv 在同步环境时处理。在项目目录中执行以下命令。

```shell
uv sync --locked
uv run rag-knowledge-base
```

运行后应显示 `RAG knowledge base project is ready.`。`pyproject.toml` 声明项目信息与依赖，`uv.lock` 保存解析结果，`.python-version` 记录 Python 版本选择，`.venv/` 保存本地虚拟环境。

`uv run python -m rag_knowledge_base` 与原有的 `uv run python main.py` 也会调用同一个入口。

## 开始第一课

课程给定的三个样本文档已放在 `data/docs/`。以该目录为语料根目录时，文档编号分别为 `超时.md`、`日志.md`、`预算.md`。各文件采用课程中的例句，并按仓库 Markdown 规范添加同名一级标题。读取时保留完整文件内容，包括标题标记。

按[文档与关键词检索](../../notes/rag/retrieval-and-documents.md)任务 1，文档记录包含 `doc_id`、`title`、`text`、`source` 四个字符串字段。

`load_documents` 接收语料根目录，读取该目录及其各级子目录中的 `.txt`、`.md` 文件，扩展名匹配不区分大小写。编号和来源都采用相对于语料根目录的路径，标题取文件名去掉扩展名的部分。正文按 UTF-8 读取，统一换行并清除首尾空白，保留 Markdown 标记。空文件和只有空白的文件会被跳过，日志记录文件路径与原因；读取或解码失败时抛出异常。

在项目目录运行 `uv run python` 后，可以直接调用目录读取函数。

```python
from pathlib import Path
from rag_knowledge_base.document_loader import load_documents

documents = load_documents(Path("data/docs"))
print(len(documents))
print([document.doc_id for document in documents])
```

当前三个样本应返回三条文档记录。返回列表的顺序不作为文档编号的依据。

测试使用 Python 标准库 `unittest`，在项目目录执行以下命令。

```shell
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

当前测试覆盖单文件和目录读取，包括文档字段与正文清理、子目录遍历、文件筛选、编号稳定性、空文件日志，以及读取和解码失败。测试自行构造练习文件，不依赖个人资料。

## 切换编辑器环境

在仓库根目录运行下面的命令，让共享配置及正在运行的 VS Code、Cursor 使用本项目的解释器。

```shell
use-venv projects/rag-knowledge-base --editor both
```

已有终端继续保留原来的环境。切换完成后新建终端，再用 `python -c "import sys; print(sys.executable)"` 核对解释器路径。
