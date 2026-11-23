# RAG Knowledge Base

本项目配套 [RAG 检索基础](../../notes/rag/foundations/index.md)，使用 Python 读取本地文档，并通过关键词或向量方法检索。

项目使用独立虚拟环境，包含 50 篇练习文档。命令行可以列出已载入的文档，也能按编号查看原文。输入查询时，程序会返回匹配的片段、分数和原文位置。

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
│       ├── keyword_retrieval.py
│       └── vector_retrieval.py
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

`cli.py` 负责参数解析和结果展示。`--query` 使用 `chunking.py` 将文档切成片段，向量查询在处理问题前为这批片段生成向量，供本次调用中的多个问题复用。`document.py` 定义文档记录类型，`document_loader.py` 提供单文件和目录读取函数。`__init__.py` 标记 Python 包，`__main__.py` 支持通过模块名运行。根目录的 `main.py` 转调同一个入口。

`keyword_retrieval.py` 用 `tokenize` 为查询和候选文本分词。候选的标题和正文都参与计分，分数是候选与查询共有的词项数。`search_keywords` 检索整篇文档，`search_chunk_keywords` 用同样的规则检索片段。两个函数都返回候选及其分数，最多取前 K 个正分结果。空查询或无匹配时返回空列表，无效 K 抛出 `ValueError`。

`embedding.py` 使用 Sentence Transformers 为问题、文档和片段生成向量。文档与片段在编码前都要检查完整输入的长度，输入包含前缀、标题和正文。编码结果要通过有效性和维度检查，批量结果按文档编号或片段编号保存。`similarity.py` 提供向量校验和余弦相似度计算。

`vector_retrieval.py` 中的 `search_vectors` 比较问题和文档的向量，`search_chunk_vectors` 比较问题和片段的向量。两者都用编号将候选与向量对应起来，按余弦相似度排序，返回候选及其分数。查询为空白或候选为空时直接返回空列表。无效 K 或向量字典的编号与候选不符时抛出 `ValueError`。

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

使用 `--query` 输入查询，通过 `--method` 选择检索方法。

```shell
uv run rag-knowledge-base data/docs --query "请求超时" --method keyword --k 5
```

`--method` 接受 `keyword` 和 `vector`，省略时使用 `keyword`。`--k` 是最多返回的片段数，默认是 5，必须为正整数。结果按分数降序排列，同分按片段编号升序。每条结果显示片段编号、标题、正文、来源、分数和原文区间。

关键词方法按共同词项个数计分，只返回正分片段。向量方法按余弦相似度计分，零分和负分也参与排序。

向量方法使用固定修订的 `intfloat/multilingual-e5-small` 和 CPU，模型文件缓存于仓库根目录的 `.cache/huggingface/`。首次使用需要准备模型文件。模型已经缓存时，可以通过 Hugging Face Hub 的 `HF_HUB_OFFLINE=1` 设置离线运行。

同一次调用可以重复提供 `--query`。程序先切好这批文档，再按输入顺序处理问题。使用向量方法时，每个片段编码一次，所得向量供本次调用的所有问题使用。

```shell
HF_HUB_OFFLINE=1 uv run rag-knowledge-base data/docs --method vector --k 5 \
  --query "请求一直没有返回怎么办？" \
  --query "怎样记录请求耗时？" \
  --query "发送前怎样检查上下文长度？"
```

多个问题的结果各自带有查询标题，单问题调用直接展示检索结果。片段向量保存在本次进程的内存中。

`--query`、`--doc-id` 和 `--evaluate` 每次最多选一个。三个参数都省略时，程序显示文档列表。查询为空白（例如 `--query ""`）或语料为空时，程序显示 `未找到匹配的chunk` 并正常退出。关键词查询仅含标点或没有共同词项时，也会显示这句提示。

入口参数冲突、检索方法无效或 K 无效时，程序向标准错误输出报告原因，以状态码 2 退出。片段的编码输入超出长度上限，或模型返回无效向量时，向量查询也按这个方式报错。

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

### 固定长度切块

在项目目录运行 `uv run python`，执行下面的代码。先用 `load_documents` 读取语料，再把文档列表交给 `prepare_chunks` 切块。

```python
from pathlib import Path

from rag_knowledge_base.chunking import prepare_chunks
from rag_knowledge_base.document_loader import load_documents

documents = load_documents(Path("data/docs"))
chunks = prepare_chunks(
    documents, document_version="v1", chunk_size=100, overlap=20
)
```

示例沿用 `--query` 的切块配置。`v1` 标记资料版本。`chunk_size` 和 `overlap` 分别指定单块的长度上限和相邻片段的重叠量，单位都是 Unicode 码点。

每个片段的 `start` 和 `end` 记录它在清理后的文档正文中的起止位置。要回查片段，按 `chunk.doc_id` 找到所属文档，再取 `document.text[chunk.start:chunk.end]`，就能得到 `chunk.text`。

为片段生成向量时，项目把 `"passage: "`、文档标题、换行和片段正文按顺序拼起来，作为 E5 模型的输入。[片段编码实现](src/rag_knowledge_base/embedding.py)

## 批量评测

在项目目录运行下面的命令，用固定的 20 道题做文档级关键词检索评测，每题最多取 3 篇文档。输出会列出每道题的排名、指标和查询耗时，最后分别统计有答案和无答案的题数，并汇总有答案题的指标。

```shell
uv run rag-knowledge-base data/docs --evaluate data/evaluation/v1/queries.json --method keyword --k 3
```

要复现关键词和向量检索在 K 为 1、3、5 时的完整对比，见[第四课评测记录](../../notes/rag/foundations/answers/retrieval-evaluation.md)中的“复现命令”。同一份报告也保存了六次运行的逐题结果，以及分析中引用的原文。

## 测试

测试使用 Python 标准库 `unittest`，在项目目录执行以下命令。

```shell
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

默认测试套件可离线运行，真实模型集成测试需要单独启用。离线测试覆盖单文件和目录读取、正文清理、子目录遍历、文件筛选、编号稳定性、空文件日志，以及读取和解码失败。命令行测试通过模块入口和 `main()` 验证列表、按编号查看、片段检索、批量评测、帮助信息和失败退出。测试自行构造练习文件。

命令行检索测试从查询入口开始，实际加载测试文件，核对排名、分数和片段正文。测试还检查同一篇文档的两块能同时返回，并且各自可以按区间回查。其余用例覆盖默认参数、同分排序、K 超过匹配数、K 为 1、空查询、无匹配与空目录。错误用例核对错误类别和退出状态。

向量入口测试用模型替身提供分词和编码结果，由应用完成切块、查询编码、相似度计算与原文展示。多问题用例检查片段编码是否只做一批，以及每个非空问题的结果是否正确分组。超长输入用例核对报错时模型尚未编码，非法向量用例核对校验失败时尚未计算相似度。

词项切分测试直接调用函数，验证相邻双字切分、单字保留、英文大小写统一、去重、标点和空白分隔、中英文混合及空输入。

单篇文档计分测试直接调用函数，验证课程样例分数、标题和正文共同计分、重复词项只计一次，以及标题与正文之间不会拼接出词项。空查询词项或无匹配时得 0 分，编号和来源不参与计分。

批量检索测试直接调用 `search_keywords`，验证课程样例排名、零分过滤、前 K 项截取、同分排序、空查询、无匹配和空文档集合，并检查无效 K 在查询或文档集合为空时仍会报错。

向量检索组件测试直接调用 `search_vectors`，验证全部分数参与排序、同分按编号排序、相近分数保留精度、K 边界、空输入、编号集合不符和查询向量检查失败时的执行边界。

编码测试使用模型替身，覆盖问题与文档的前缀、归一化参数、输出格式、输入长度边界、编号对应、非法向量拒绝和模型声明维度的变化。余弦测试覆盖计算精度、方向关系、不同维度与非法输入。

真实模型集成测试放在 `tests/test_embedding_integration.py`。在项目目录显式启用后，测试先编码三篇固定文档和三条问题，再准备完整语料。

```shell
RAG_RUN_REAL_EMBEDDING_TESTS=1 uv run python -m unittest discover -s tests -p 'test_embedding_integration.py' -v
```

测试固定模型修订并使用 CPU，首次运行会下载模型文件到仓库根目录的 `.cache/huggingface/`。模型已缓存时，可添加 Hugging Face Hub 的 `HF_HUB_OFFLINE=1` 设置离线复测。模型配置、实际维度、两种方法的真实语料试查结果及原文核对，见[Embedding 与逐篇检索任务验收记录](../../notes/rag/foundations/answers/embeddings-and-search.md)。

任务验收与试查观察见[文档与关键词检索练习回答](../../notes/rag/foundations/answers/retrieval-and-documents.md)。

## 代码质量检查

在本项目目录运行以下命令。两条命令都使用仓库中 Python 基础项目锁定的 Ruff 版本。第一条检查当前目录下的 Python 文件是否符合格式要求，第二条运行 lint。

```shell
uv run --project ../python --locked ruff format --check .
uv run --project ../python --locked ruff check .
```

## 切换编辑器环境

在仓库根目录运行下面的命令，让共享配置及正在运行的 VS Code、Cursor 使用本项目的解释器。

```shell
use-venv projects/rag-knowledge-base --editor both
```

已有终端继续保留原来的环境。切换完成后新建终端，再用 `python -c "import sys; print(sys.executable)"` 核对解释器路径。
