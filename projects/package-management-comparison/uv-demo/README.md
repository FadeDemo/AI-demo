# uv-demo

本项目用于练习 uv 的项目初始化、依赖声明、锁定、同步和命令执行。它是一个可安装项目，`uv init --package` 生成的构建系统负责把 `src/uv_demo` 和 `uv-demo` 命令安装进项目环境。

## 安装与运行

```shell
uv sync
uv run uv-demo
uv run python -c "import httpx; print(httpx.__version__)"
```

`uv sync` 根据 `pyproject.toml` 和 `uv.lock` 恢复环境，`uv run` 会在项目环境中执行命令。

## 验证

```shell
uv lock --check
uv run ruff format --check src
uv run ruff check src
uv run pytest --version
```

本项目没有业务测试用例；验收重点是锁文件一致性、项目安装、命令入口以及格式和 Lint。

课程说明见 [Python 包管理](../../../notes/python/package-management.md)。
