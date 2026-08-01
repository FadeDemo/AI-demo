# Python 课程示例

这个目录统一保存 [Python 工程基础课程](../../notes/python/index.md) 的可运行代码、测试和样本数据。目前已完成[文件处理](../../notes/python/file-handling.md)练习与自动化验收；[虚拟环境](../../notes/python/virtual-environments.md)使用本项目验证隔离和重建，[包管理](../../notes/python/package-management.md)另有 [pip 与 uv 对照项目](../package-management-comparison/README.md)。示例程序仅使用 Python 标准库，项目使用 Ruff 开发依赖统一格式化和 Lint。

文件处理以及可共用同一环境的后续 Python 示例继续放在本项目中；需要比较不同环境或依赖管理方式的课程则使用独立项目，避免互相修改配置和锁文件。

## 环境要求

- Python 3.11 或更高版本
- 可选：当前受支持版本的 `uv`

## 运行示例

从仓库根目录执行：

```shell
cd projects/python
uv run python file_handling_demo.py
```

没有安装 `uv` 时，也可以直接使用匹配版本的 Python：

```shell
cd projects/python
python3 file_handling_demo.py
```

`file_handling_demo.py` 是用于串联主要读取流程的综合演示，也是快速确认示例数据可用的入口；它不是课程中每个代码块的逐段副本。笔记中的代码块可以在该项目根目录下单独运行，并复用 `data/` 中的数据。

运行上面的 `uv run` 或 `python3` 命令后，程序会读取 `data/` 中的 Markdown、TXT、JSON、JSON Lines 和 CSV 文件并打印摘要，其中的关键输出如下：

```text
Markdown title: # 文件处理示例
JSONL records: 3
CSV rows: 3
Documents: ['faq.txt', 'guide.md', 'metadata.json']
```

## 运行测试

测试使用标准库 `unittest`：

```shell
uv run python -m unittest discover -s tests -v
```

## 检查代码质量

Ruff 由 uv 作为开发依赖安装，用于格式化和 lint Python 文件：

```shell
uv run ruff format --check .
uv run ruff check .
```

## 目录结构

```text
python/
├── data/                       # 随仓库提交的测试数据
│   ├── knowledge/              # 递归遍历示例使用的小型知识库
│   ├── articles.csv
│   ├── config.json
│   ├── documents.jsonl
│   └── large-corpus.txt
├── exercises/
│   └── file_handling/
│       └── load_documents.py   # 文件处理练习代码
├── tests/
│   ├── __init__.py
│   ├── test_document_loader.py
│   └── test_file_handling_exercise.py
├── file_handling_demo.py       # 串联主要文件读取流程
├── document_loader.py          # 可复用的文件读取函数
└── pyproject.toml              # Python 版本与项目配置
```

测试数据只用于教学，内容不包含密钥或个人信息。运行示例不会修改这些输入文件。
