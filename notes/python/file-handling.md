---
title: Python 文件处理
type: concept
area: python
status: learning
created: 2026-07-21
updated: 2026-07-22
tags:
  - python
  - files
  - rag
---

# Python 文件处理

文件处理是把资料读入 RAG 系统的第一步。本阶段的目标是把本地文件可靠地转换成格式统一的 Python 对象，而不是一开始就掌握复杂的 PDF 或 Markdown 解析工具。

## 配套示例与测试数据

本文示例中的 `data/...` 都是相对于 [Python 课程示例项目](../../projects/python/README.md) 根目录的路径。先从仓库根目录进入该项目，后续代码块即可直接使用这些相对路径：

```shell
cd projects/python
uv run python file_handling_demo.py
```

如果没有安装 `uv`，也可以运行 `python3 file_handling_demo.py`。示例程序只使用 Python 标准库，项目包含 Markdown、TXT、JSON、JSON Lines 和 CSV 测试数据。下面的命令会运行配套单元测试，既检查各类数据的读取结果，也验证无效 JSON Lines 能否报告具体的出错行：

```shell
uv run python -m unittest discover -s tests -v
```

## 1. 路径与文件系统

推荐使用标准库 `pathlib`，它比手工拼接路径字符串更清晰，也能减少不同操作系统之间的路径差异。

```python
from pathlib import Path

knowledge_dir = Path("data/knowledge")
document_path = knowledge_dir / "guide.md"

print(document_path.name)    # guide.md
print(document_path.suffix)  # .md
print(document_path.exists())  # True
```

相对路径既不是相对于 Python 解释器所在目录，也不会自动相对于源码文件所在目录。操作系统会根据 Python 进程的当前工作目录解析相对路径，这个目录通常是执行命令时终端所在的位置，也可以由编辑器或启动配置指定。例如，在 `projects/python` 中运行 `.venv/bin/python examples/file_handling/01_paths.py` 时，解释器位于 `.venv/bin/`，源码位于 `examples/file_handling/`，但 `Path("data/knowledge")` 仍然从工作目录 `projects/python` 开始查找。

遇到“文件明明存在却找不到”时，可以打印当前工作目录和目标文件解析后的完整路径，确认程序实际会到哪里查找文件：

```python
from pathlib import Path

print(Path.cwd())
print(Path("data/knowledge").resolve())
```

如果解析后的路径没有指向 `projects/python/data/knowledge`，应先进入 `projects/python` 再运行示例，或者根据实际工作目录调整传入的相对路径。

不要依赖某台电脑上的绝对路径。项目内的输入目录应通过相对路径、配置项或命令行参数指定。

## 2. 读取与写入文本

TXT 和 Markdown 都可以先按普通 UTF-8 文本读取。Markdown 的标题、列表和代码块此时只是文本内容，不需要专门的解析工具。

```python
from pathlib import Path

path = Path("data/knowledge/guide.md")
content = path.read_text(encoding="utf-8")
```

写入文本时应明确编码。下面的示例将结果写入仓库约定的临时目录 `.agent-tmp/`，避免运行示例后产生需要提交的数据变更：

```python
from pathlib import Path

output_path = Path("../../.agent-tmp/python-file-handling/cleaned.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("清洗后的内容\n", encoding="utf-8")
```

`output_path.parent` 表示目标文件所在的父目录。`mkdir()` 用来创建该目录；`parents=True` 会同时创建缺失的上级目录，`exist_ok=True` 则允许目录已经存在。`write_text()` 可以创建或覆盖文件，但不会自动创建父目录，因此写入前需要先确保父目录存在，否则会触发 `FileNotFoundError`。

`read_text()` 适合能够一次放入内存的小型文本。处理很大的日志或语料文件时，应逐行读取：

```python
from pathlib import Path

path = Path("data/large-corpus.txt")

with path.open("r", encoding="utf-8") as file:
    for line in file:
        normalized = line.strip()
        if normalized:
            print(normalized)
```

`with` 会管理文件的打开和关闭。即使读取过程中发生异常，文件也会被正确关闭。

## 3. JSON 与 JSON Lines

JSON 文件保存一个完整的 JSON 值，常见形式是对象或数组。使用 `json.load()` 可以直接从文件对象读取：

```python
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


config = read_json(Path("data/config.json"))
print(config["language"])  # zh-CN
```

写入时使用 `ensure_ascii=False` 保留可读的中文，使用 `indent` 便于人工检查。输出仍放在仓库约定的 `.agent-tmp/` 中：

```python
import json
from pathlib import Path

records = [{"title": "向量检索", "status": "learning"}]
path = Path("../../.agent-tmp/python-file-handling/records.json")
path.parent.mkdir(parents=True, exist_ok=True)

with path.open("w", encoding="utf-8") as file:
    json.dump(records, file, ensure_ascii=False, indent=2)
```

JSON Lines 通常使用 `.jsonl` 后缀，每行是一个独立 JSON 对象，适合逐条处理大量记录：

```python
import json
from pathlib import Path

path = Path("data/documents.jsonl")

with path.open("r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        if line.strip():
            record = json.loads(line)
            print(line_number, record)
```

示例数据共有 3 行有效记录，因此输出的行号是 1、2、3。真实数据可能有空行，所以解析前先使用 `line.strip()` 检查。

## 4. CSV 与表格数据

小型 CSV 可以使用标准库 `csv`，不需要为了简单读取立即引入 pandas：

```python
import csv
from pathlib import Path

path = Path("data/articles.csv")

with path.open("r", encoding="utf-8", newline="") as file:
    rows = list(csv.DictReader(file))

print(rows[0]["title"])  # 路径基础
print(len(rows))  # 3
```

当任务涉及缺失值、类型转换、筛选、聚合或大型表格分析时，再考虑在项目运行时依赖中加入 pandas。当前配套示例程序只使用标准库，避免读者在学习文件 API 前先处理第三方运行时依赖。

CSV 可能使用逗号之外的分隔符，也可能采用 UTF-8 之外的编码。不能正确读取时，应先确认数据来源的格式约定，不要盲目忽略解码错误。

## 5. 遍历目录与筛选文件

`Path.rglob()` 可以查找当前目录及其所有子目录中的文件，这种查找方式也叫递归查找：

```python
from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}
knowledge_dir = Path("data/knowledge")

paths = sorted(
    path
    for path in knowledge_dir.rglob("*")
    if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
)
```

排序不是读取文件所必需的，但能让运行顺序稳定，便于测试和排查问题。实际项目还应决定是否跳过隐藏文件、缓存目录、符号链接和超大文件。

## 6. 转换为统一文档对象

不同文件最终应转换成统一结构，方便后面的文本切块、将文本转换为向量（Embedding）和检索代码处理。可以先使用标准库的 `dataclass` 来定义这种文档对象：

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


def read_text_document(path: Path, root: Path) -> Document:
    content = path.read_text(encoding="utf-8")
    return Document(
        content=content,
        source=path.relative_to(root).as_posix(),
        metadata={
            "file_name": path.name,
            "file_type": path.suffix.lower(),
        },
    )


root = Path("data/knowledge")
document = read_text_document(root / "guide.md", root)
print(document.source)  # guide.md
print(document.metadata["file_type"])  # .md
```

`source` 应尽量保存稳定、可展示的相对路径。`metadata` 用来保存文件名、文件类型等附加信息。之后生成答案引用时，可以根据这些信息告诉用户内容来自哪个文件。

## 7. Markdown 需要结构化解析吗

入门阶段不需要。先把 Markdown 当作 UTF-8 文本读取，再按空行、字符数或简单标题规则切块即可。

只有当检索质量需要利用文档结构时，才逐步增加：

- 提取文档开头的 YAML 信息区（Front Matter），保存为 `metadata`。
- 按标题层级切分章节，并让子块继承章节标题。
- 区分正文、代码块、表格和链接。
- 使用 Markdown 解析工具生成表示文档结构的语法树，避免简单正则表达式误判复杂结构。

是否引入解析工具，应根据文档复杂程度和检索效果决定，而不是只看文件扩展名。

## 8. 异常处理与日志

文件不存在、没有权限、编码错误和内容格式错误需要区别处理。捕获异常时不要只输出模糊信息，也不要无条件吞掉所有异常。

```python
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json_document(path: Path) -> object | None:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error("文件不存在: %s", path)
    except UnicodeDecodeError:
        logger.error("文件不是有效的 UTF-8 文本: %s", path)
    except json.JSONDecodeError as error:
        logger.error("JSON 格式错误: path=%s line=%s", path, error.lineno)

    return None
```

在批量导入任务中，通常需要记录单个失败并继续处理其他文件，最后汇总成功数和失败数；如果关键配置文件读取失败，则更适合立即终止。

## 9. PDF 等文件为什么不能直接读成文本

PDF、Word 文档和图片通常是二进制格式，不能对它们直接使用 `read_text()`。RAG 项目一般通过对应解析库提取文本、页码和标题，再把解析结果转换成统一的 `Document`：

```text
PDF 文件 → PDF 解析工具 → 每页文本与页码 → Document 列表
扫描版 PDF → 页面图像 → 图片文字识别（OCR）→ 文本与页码 → Document 列表
```

前置阶段不要求理解这些文件格式的内部结构，也不要求自己编写解析器。只需要知道文件读取和内容解析是两个步骤：`path.read_bytes()` 只能取得原始字节，不会自动得到可检索文本。

处理复杂格式时，还要检查表格、双栏排版、页眉页脚和扫描质量。引入第三方解析工具后，应把它记录在项目配置中，并用实际文档样本验证文本提取效果。

## 10. 安全与可靠性

- 不要把用户传入的文件名直接拼接到输出路径，应验证解析后的路径仍位于允许目录内。
- 不要加载来源不可信的 `pickle` 文件，Python 还原其中对象时可能执行任意代码。
- 在读取前限制允许的扩展名和文件大小，避免意外耗尽内存。
- 不要把密钥、个人信息或完整敏感文档写入日志。
- 覆盖文件前确认写入模式，`"w"` 会清空原内容后重新写入，`"a"` 才是在末尾追加。

## 11. 练习与验收

实现函数 `load_documents(root: Path) -> list[Document]`：

1. 读取目标目录及其子目录中的 `.txt`、`.md` 和 `.json`。
2. 忽略空文本和不支持的扩展名。
3. 为每个文档记录相对路径、扩展名和字节大小。
4. 某个文件失败时记录具体路径和异常类型，继续处理其余文件。
5. 保证相同目录多次运行时，结果顺序一致。

至少测试以下情况：

- 空目录返回空列表。
- 子目录中的文件能够被读取。
- 非 UTF-8 文本不会导致整个导入任务崩溃。
- 损坏的 JSON 会被记录并跳过。
- `source` 不包含本机绝对路径。

完成后继续学习[虚拟环境](virtual-environments.md)。

## 延伸阅读

- [Python pathlib 官方文档](https://docs.python.org/3/library/pathlib.html)
- [Python json 官方文档](https://docs.python.org/3/library/json.html)
- [Python csv 官方文档](https://docs.python.org/3/library/csv.html)
