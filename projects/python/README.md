# Python 课程示例

这个目录统一保存 [Python 工程基础课程](../../notes/python/index.md) 的可运行代码、测试和样本数据。目前已实现[文件处理](../../notes/python/file-handling.md)主题，项目仅使用 Python 标准库，不需要下载第三方包。

后续虚拟环境、包管理及其他 Python 主题的代码也放在此项目中；当示例增多时，再按主题增加子目录，避免在 `projects/` 下为每一课创建独立项目。

## 环境要求

- Python 3.11 或更高版本
- 可选：当前受支持版本的 `uv`

## 运行示例

从仓库根目录执行：

```shell
cd projects/python
uv run python demo.py
```

没有安装 `uv` 时，也可以直接使用匹配版本的 Python：

```shell
cd projects/python
python3 demo.py
```

示例会读取 `data/` 中的 Markdown、TXT、JSON、JSON Lines 和 CSV 文件，并打印摘要。预期输出中的关键部分如下：

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

## 目录结构

```text
python/
├── data/                       # 随仓库提交的测试数据
│   ├── knowledge/              # 递归遍历示例使用的小型知识库
│   ├── articles.csv
│   ├── config.json
│   ├── documents.jsonl
│   └── large-corpus.txt
├── tests/
│   └── test_document_loader.py
├── demo.py                     # 一次运行所有读取示例
├── document_loader.py          # 可复用的文件读取函数
└── pyproject.toml              # Python 版本与项目配置
```

测试数据只用于教学，内容不包含密钥或个人信息。运行示例不会修改这些输入文件。
