# RAG Knowledge Base

本项目配套 [RAG 检索基础](../../notes/rag/index.md)，使用 Python 读取本地文档并进行关键词检索。

项目使用独立虚拟环境，包含 50 篇练习文档。命令行入口可以显示载入数量和文档编号、按编号查看原文，也可以根据查询展示文档排名和匹配分数。

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
│       ├── document_loader.py
│       ├── embedding.py
│       ├── similarity.py
│       └── keyword_retrieval.py
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

`cli.py` 负责参数解析、文档列表、按编号查看和关键词检索结果展示。`document.py` 定义文档记录类型，`document_loader.py` 提供单文件和目录读取函数。`__init__.py` 标记 Python 包，`__main__.py` 支持通过模块名运行。根目录的 `main.py` 转调同一个入口。

`keyword_retrieval.py` 提供词项切分、单篇文档计分与批量关键词检索函数。`tokenize` 统一查询与文档文本的切分规则，`score_document` 统计查询词项与文档标题、正文词项的共同项数量。`search_keywords` 接收文档列表、查询和正整数 K，返回按分数降序、同分按编号升序排列的前 K 个正分结果，每项包含文档对象和分数。空查询或无匹配时返回空列表，无效 K 抛出 `ValueError`。

`embedding.py` 提供问题、单篇文档和批量文档编码，使用 Sentence Transformers 模型生成向量。两侧编码结果都要通过有效性与模型声明维度的检查，批量结果按文档编号保存。文档编码前会检查包含前缀、标题和正文的完整输入长度。`similarity.py` 提供单条向量检查、带输入检查的余弦比较，以及供已校验输入使用的纯计算函数。

练习文档放在 `data/docs/`，出处和使用范围记录在[语料说明](data/README.md)，测试放在 `tests/`。

## 环境与运行

项目使用 Python 3.13 和 uv，运行依赖包括 NumPy 与 Sentence Transformers。打包工具为 `uv_build`，由 uv 在同步环境时处理。在项目目录中执行以下命令。

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

使用 `--query` 输入查询，执行关键词检索。

```shell
uv run rag-knowledge-base data/docs --query "请求超时" --method keyword --k 5
```

`--method` 当前只接受 `keyword`，省略时也使用该方法。`--k` 为最多返回的文档数，默认是 5，必须为正整数。结果按分数降序排列，同分按文档编号升序排列，每项展示编号、标题、来源、完整正文和分数。零分文档不返回，匹配不足 K 篇时只展示实际匹配的文档。

`--query` 与 `--doc-id` 不能同时提供，两者都不提供时仍显示文档列表。空查询（例如 `--query ""`）、纯标点查询或无匹配时，入口显示“未找到匹配的文档”，正常退出。同时提供查询与文档编号、使用不支持的方法，或检索时 K 无效，都会报错并以状态码 2 退出；错误信息写入标准错误输出。

## 语料与文档加载

`data/docs/` 保存 50 篇 UTF-8 Markdown 短文。根目录中的 `超时.md`、`日志.md`、`预算.md` 来自课程手算样例，各自带有同名一级标题。其余 47 篇短文依据仓库课程改写，按主题放在五个子目录中。每篇围绕一个较小主题，来源和使用范围见[语料说明](data/README.md)。

文档记录包含 `doc_id`、`title`、`text`、`source` 四个字符串字段，分别保存编号、标题、正文和来源。

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

## 测试

测试使用 Python 标准库 `unittest`，在项目目录执行以下命令。

```shell
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

默认套件发现 72 项测试，其中 71 项通过，1 项真实模型集成测试按默认设置跳过。离线测试覆盖单文件和目录读取、正文清理、子目录遍历、文件筛选、编号稳定性、空文件日志，以及读取和解码失败。命令行测试从模块入口启动子进程，验证列表、按编号查看、关键词检索、帮助信息和失败退出。测试自行构造练习文件。

命令行检索测试从查询开始，实际加载测试文件并检查排名、分数和展示字段，覆盖默认参数、同分排序、K 超过匹配数、K 为 1、空查询、无匹配与空目录。错误用例检查无效 K、不支持的方法，以及查询与按编号查看互斥时的错误类别和退出状态。

词项切分测试直接调用函数，验证相邻双字切分、单字保留、英文大小写统一、去重、标点和空白分隔、中英文混合及空输入。

单篇文档计分测试直接调用函数，验证课程样例分数、标题和正文共同计分、重复词项只计一次，以及标题与正文之间不会拼接出词项。空查询词项或无匹配时得 0 分，编号和来源不参与计分。

批量检索测试直接调用 `search_keywords`，验证课程样例排名、零分过滤、前 K 项截取、同分排序、空查询、无匹配和空文档集合，并检查无效 K 在查询或文档集合为空时仍会报错。

编码测试使用模型替身，覆盖问题与文档的前缀、归一化参数、输出格式、输入长度边界、编号对应、非法向量拒绝和模型声明维度的变化。余弦测试覆盖计算精度、方向关系、不同维度与非法输入。

真实模型集成测试放在 `tests/test_embedding_integration.py`。在项目目录显式启用后，测试先编码三篇固定文档和三条问题，再准备完整语料。

```shell
RAG_RUN_REAL_EMBEDDING_TESTS=1 uv run python -m unittest discover -s tests -p 'test_embedding_integration.py' -v
```

测试固定模型修订并使用 CPU，首次运行会下载模型文件到仓库根目录的 `.cache/huggingface/`。模型已缓存时，可添加 Hugging Face Hub 的 `HF_HUB_OFFLINE=1` 设置离线复测。模型配置、实际维度和运行结果见[Embedding 与逐篇检索任务 1 验收记录](../../notes/rag/answers/embeddings-and-search.md)。

任务验收与试查观察见[文档与关键词检索练习回答](../../notes/rag/answers/retrieval-and-documents.md)。

## 切换编辑器环境

在仓库根目录运行下面的命令，让共享配置及正在运行的 VS Code、Cursor 使用本项目的解释器。

```shell
use-venv projects/rag-knowledge-base --editor both
```

已有终端继续保留原来的环境。切换完成后新建终端，再用 `python -c "import sys; print(sys.executable)"` 核对解释器路径。
