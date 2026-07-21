---
title: Python 虚拟环境
type: concept
area: python
status: learning
created: 2026-07-21
updated: 2026-07-21
tags:
  - python
  - virtual-environment
  - engineering
---

# Python 虚拟环境

虚拟环境为每个项目提供独立的 Python 包安装位置，避免不同项目对同一个包版本的要求互相冲突。这种做法通常称为“隔离依赖”。虚拟环境不等同于虚拟机或容器，也不会把数据库、环境变量和操作系统工具一起隔开。

## 1. 为什么需要虚拟环境

假设两个项目依赖不同版本的同一个库：

```text
project-a → library 1.x
project-b → library 2.x
```

如果把所有包都安装到同一个全局 Python，升级 `project-b` 的依赖可能破坏 `project-a`。独立环境会为两个项目分别保存已安装包。

虚拟环境还能避免：

- 使用管理员权限修改系统 Python。
- 电脑上能运行、换一台机器却不知道缺少哪些依赖。
- `pip` 与 `python` 指向不同安装位置。
- 调试时无法判断某个包来自哪个环境。

## 2. Python 解释器、环境与依赖的区别

- Python 解释器负责执行代码，例如 Python 3.12。
- 虚拟环境保存某个项目使用的解释器入口和包安装目录。
- 依赖是项目需要的第三方包；版本约束说明项目允许使用哪些版本。
- 锁文件记录最终选定的准确版本，用于在其他电脑上搭建出一致的环境。

虚拟环境目录本身通常不提交 Git，因为它体积较大、包含机器相关路径，而且能根据项目配置重新创建。

## 3. 使用标准库 venv

在项目根目录创建名为 `.venv` 的环境：

```shell
python3 -m venv .venv
```

在 macOS 或 Linux 中激活：

```shell
source .venv/bin/activate
```

在 Windows PowerShell 中激活：

```powershell
.venv\Scripts\Activate.ps1
```

激活后检查当前解释器：

```shell
python -c "import sys; print(sys.executable)"
python -m pip --version
```

结束工作时退出环境：

```shell
deactivate
```

激活并不是环境存在的必要条件，它只是临时修改当前终端查找命令时使用的 `PATH`。也可以直接执行 `.venv/bin/python`，编辑器和自动化脚本通常就是直接选择解释器路径。

## 4. 使用 uv 管理项目环境

本仓库约定未来的 Python 项目使用 `uv` 记录、安装和运行第三方包。已有 `pyproject.toml` 的项目通常执行：

```shell
uv sync
uv run python --version
```

`uv sync` 会根据 `pyproject.toml` 和锁文件安装正确版本的包，`uv run` 会在项目环境中执行命令，无需手动激活。

创建新项目时可以使用：

```shell
uv init document-loader
cd document-loader
uv add pytest --dev
uv run pytest
```

如果只是为现有目录创建环境，可以使用：

```shell
uv venv
```

不要在同一个项目中随意混用多套环境和依赖管理方式。团队选定 `uv` 后，应使用项目的 `pyproject.toml` 与 `uv.lock` 完成安装、运行和更新。

## 5. 应该提交哪些文件

一般应提交：

- `pyproject.toml`：项目名称、版本、直接使用的第三方包和工具配置。
- `uv.lock`：所有包最终选定的准确版本。
- `.python-version`：如果项目用它记录期望的 Python 版本。
- 源码、测试和环境搭建说明。

一般不应提交：

- `.venv/`：本地生成的虚拟环境。
- `__pycache__/`：Python 运行代码时自动生成的缓存。
- `.env`：经常包含密钥或本机配置。
- 编辑器保存的本机解释器路径。

应在 `.gitignore` 中排除生成文件，但仍需在提交前检查 Git 暂存区中的改动，不能把 `.gitignore` 当作敏感信息保护机制。

## 6. 常见问题排查

### 安装成功但无法导入

先检查安装包和运行代码是否使用同一个解释器：

```shell
python -c "import sys; print(sys.executable)"
python -m pip --version
```

与直接运行 `pip` 相比，`python -m pip` 更明确地把 pip 绑定到当前 Python。

### 编辑器仍然标红

终端激活环境不会保证编辑器自动切换解释器。需要在编辑器中选择项目 `.venv` 对应的 Python，然后重启编辑器的 Python 插件或终端。

### 终端前面没有环境名称

命令提示符是否显示 `(.venv)` 取决于 shell 配置，不能单凭显示判断。应检查 `sys.executable`，或使用 `uv run` 明确执行环境。

### 重建环境后问题消失

这通常说明实际安装的包已经与项目配置不一致。环境应该是可以删除和重建的临时产物；真正需要维护的是 `pyproject.toml` 和锁文件。

## 7. 练习与验收

1. 创建一个空项目和 `.venv`。
2. 在环境中安装一个第三方包并成功导入。
3. 证明系统 Python 和虚拟环境中的包列表不同。
4. 删除环境后，根据项目依赖文件重新创建它。
5. 配置编辑器使用重建后的环境并运行测试。

你应该能够解释：

- 为什么不建议使用管理员权限向系统 Python 安装项目依赖？
- 激活虚拟环境实际修改了什么？
- 为什么 `.venv/` 不应提交，而锁文件通常应提交？
- `uv run` 为什么可以在不激活环境的情况下工作？

完成后继续学习[包管理](package-management.md)。

## 延伸阅读

- [Python venv 官方文档](https://docs.python.org/3/library/venv.html)
- [uv 项目入门指南](https://docs.astral.sh/uv/guides/projects/)
- [uv 项目结构与文件](https://docs.astral.sh/uv/concepts/projects/layout/)
