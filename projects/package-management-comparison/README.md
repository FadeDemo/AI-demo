# Python 包管理对照练习

本项目对照两种 Python 依赖管理工作流：

- [pip-demo](pip-demo/README.md)：开发者手工维护 `pyproject.toml`，使用 `venv` 和 pip 安装项目及依赖。
- [uv-demo](uv-demo/README.md)：使用 uv 维护项目声明、环境和 `uv.lock`。

两个示例使用相同的运行时依赖和开发依赖约束，并各自创建 `.venv`。不要共用环境。

## 目标

- 区分当前项目、运行时依赖和开发依赖。
- 比较 `pip install .` 与 `uv add` 对项目声明的不同影响。
- 验证安装项目自身后生成的命令入口。
- 比较无锁版本范围与锁文件在环境恢复方面的保证。

## 验收方法

分别按照两个子项目 README 完成安装、运行、格式和 Lint 检查。随后删除各自可重建的 `.venv`，仅根据仓库文件恢复环境并重复验证。

`pip-demo` 不提交锁文件是本课程刻意保留的教学例外，用于展示只有版本范围时不能保证以后解析出完全相同的版本；它不是仓库其他 Python 项目的依赖管理模板。

## 验收结果

2026-08-01 已从两个空环境完成恢复和验证：

- 两个项目均安装了 HTTPX 0.28.1、pytest 8.4.2 和 Ruff 0.16.1。
- `pip-demo` 与 `uv-demo` 命令均可在源码目录外从对应环境执行。
- pip 依赖完整性检查、两个项目的 Ruff 格式检查和 Lint 均通过。
- `uv.lock` 与 `uv-demo/pyproject.toml` 一致，`uv-demo` 项目元数据可从重建后的环境读取。

完整课程说明见 [Python 包管理](../../notes/python/package-management.md)。
