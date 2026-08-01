# pip-demo

本项目用于练习 `venv`、pip、`pyproject.toml` 和 Python 构建后端之间的分工。它是教学用对照项目，故意不提交锁文件，以便观察只有版本范围时无法保证精确复现。

## 安装与运行

以下命令适用于 macOS 和 Linux：

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m pip install --group dev
python main.py
pip-demo
```

`python -m pip install .` 会安装当前项目及其运行时依赖；第二条安装命令额外安装开发依赖。安装后生成的 `pip-demo` 命令来自当前虚拟环境。

## 验证

```shell
python -m pip check
ruff format --check main.py
ruff check main.py
pytest --version
python -m pip freeze
```

本项目没有业务测试用例；验收重点是项目安装、命令入口、依赖一致性以及格式和 Lint。

完成后使用 `deactivate` 退出虚拟环境。课程说明见 [Python 包管理](../../../notes/python/package-management.md)。
