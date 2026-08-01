---
title: Python 包管理
type: concept
area: python
status: completed
created: 2026-07-21
updated: 2026-08-01
tags:
  - python
  - dependencies
  - uv
---

# Python 包管理

包管理解决的是“项目需要哪些第三方包、允许使用哪些版本、实际安装了哪些版本，以及其他人如何重新搭建环境”。它与虚拟环境配合使用，但两者不是同一个概念。

这门课先讲与工具无关的概念，再用具体工具练习。本仓库选择 `uv` 管理 [Python 课程示例项目](../../projects/python/README.md)，所以部分命令会使用 `uv`；这只是仓库约定，并不表示 Python 项目必须使用 `uv`。已有项目可能使用 `pip` 与 `requirements.txt`、Poetry、PDM 或 Conda，应先遵循项目现有约定。

## 1. 代码里的模块、包与安装名称

- 模块通常是一个 `.py` 文件。
- Python 包通常是一组可以导入的模块。
- 安装名称是执行 `uv add` 或 `pip install` 时使用的名称。
- 导入名是代码在 `import` 后使用的名称。

安装名称和导入名不一定相同，因此不能只看 `import` 语句就猜测应该安装哪个包。应查看该项目的官方文档和发布页。

## 2. 区分声明、解析、安装与隔离

包管理工具常把几个步骤合在一条命令中，但它们解决的是不同问题：

- **声明依赖**：记录项目直接需要哪些包，以及允许的版本范围。
- **解析依赖**：结合直接依赖和传递依赖，选择一组彼此兼容的版本。
- **安装依赖**：把解析后的包放入某个 Python 环境。
- **隔离环境**：防止不同项目的依赖互相影响，这是虚拟环境负责的工作。

例如，下面的命令只保证把包安装到当前环境：

```shell
python -m pip install httpx
```

它不会自动把 `httpx` 写入项目配置。其他人只拿到源码时，仍然不知道项目依赖它。要让项目能在其他电脑上重新搭建，至少需要：

1. 把代码直接使用的第三方包写入项目文件。
2. 用所选工具解析出兼容的版本；需要可重复部署时，再记录准确结果。
3. 提供统一的同步和运行命令。

## 3. 使用 pyproject.toml 记录项目依赖

现代 Python 项目通常使用 `pyproject.toml` 保存项目名称、版本、所需 Python 版本和第三方包：

```toml
[project]
name = "document-loader"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.28,<1",
]

[dependency-groups]
dev = [
  "pytest>=8,<9",
  "ruff>=0.12,<1",
]
```

运行时依赖是程序正常工作所需的包；开发依赖只用于测试、Lint、格式化或构建。不要把所有工具都混进运行时依赖。

`pyproject.toml` 是项目元数据和构建配置的标准入口，不属于 `uv` 专用格式。不同工具都可以读取其中的标准字段，也可能在各自的工具表中保存额外设置。

依赖也可以记录在 `requirements.txt` 等文件中。重要的不是文件名越多越好，而是团队明确每个文件的用途、哪一份是主要来源，以及其他文件如何生成。

## 4. 常见工具分别负责什么

下面的对比关注工具定位，不是排名：

| 方案           | 主要能力                                                      | 适合先注意的限制                                                 |
| -------------- | ------------------------------------------------------------- | ---------------------------------------------------------------- |
| `venv` + `pip` | Python 自带环境隔离，配合官方安装器安装包；通用、容易遇到     | `pip` 不创建环境，也不会替你维护项目声明；项目工作流需要自行组合 |
| `uv`           | 管理 Python、环境、依赖、锁文件和命令执行，速度快且工作流集中 | 属于额外工具，团队和部署环境需要采用同一约定                     |
| Poetry / PDM   | 提供项目初始化、依赖声明、锁定、构建和发布等一体化工作流      | 命令和锁文件是工具自己的约定，切换工具需要迁移                   |
| Conda          | 同时管理 Python 包与部分非 Python 二进制依赖，也能管理环境    | 使用不同的包仓库和解析模型，不能简单等同于 `pip` 或 `uv`         |

选择工具时，优先考虑已有项目约定、部署平台支持、是否需要锁文件或工作区、团队熟悉程度和维护成本。学习者应先理解依赖声明、解析和环境隔离，再学习命令；这样换工具时不需要重新理解包管理。

## 5. 两种方式完成一次安装

### 使用 venv 与 pip 理解基础步骤

在类 Unix 系统中，可以显式创建和激活环境，再安装包：

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "httpx>=0.28,<1"
python -m pip show httpx
```

Windows 的激活命令不同，但环境隔离和安装的概念相同。激活后使用 `python -m pip`，可以更明确地把 `pip` 绑定到当前 Python。

此时 `httpx` 仍然只存在于本机环境中。`pip install` 不会自动修改 `pyproject.toml`：如果项目以 `pyproject.toml` 为依赖声明，开发者需要自己把 `httpx` 写入 `[project].dependencies`，再用 `python -m pip install .` 安装当前项目及其运行时依赖。较新的 pip 还可以用 `python -m pip install --group dev` 安装 `[dependency-groups]` 中的开发依赖。

另一种项目约定是维护 `requirements.txt`，再执行 `python -m pip install -r requirements.txt`。`pip freeze` 可以输出当前环境的完整快照，但快照会同时包含直接依赖和传递依赖，不能代替对直接依赖的判断，也不会回写 `pyproject.toml`。

### 使用本仓库选择的 uv 工作流

先查看示例项目的最小配置，再运行它：

```shell
cd projects/python
uv sync
uv run python file_handling_demo.py
uv run python -m unittest discover -s tests -v
```

这组命令会同步开发工具 Ruff，但示例程序本身没有第三方运行时依赖。这里的 `uv sync` 同时完成解析、安装和环境同步，`uv run` 则在项目环境中执行命令。

本仓库若新增运行时依赖，可以执行：

```shell
uv add httpx
```

仅供开发使用的工具应进入开发依赖组：

```shell
uv add pytest ruff --dev
```

移除依赖时执行：

```shell
uv remove httpx
```

`uv add` 和 `uv remove` 的价值不只是安装或卸载：它们还会同步修改依赖声明和锁文件。使用其他工具时，应找出对应的“声明、锁定、同步”命令，而不是机械照搬 `uv` 的命令名。

## 6. 版本约束、锁文件与 requirements 文件

版本号经常采用 `主版本.次版本.修订版本` 的形式，但具体兼容性仍以项目自身承诺为准。

版本约束是项目允许使用的版本范围；锁文件则是包管理器生成的文件，记录最终选中的准确版本。

常见约束示例：

```text
httpx>=0.28,<1
pytest==8.4.1
```

允许多个版本更容易获得修复和新功能，但以后安装时选中的版本可能变化；只允许一个准确版本更稳定，却需要主动更新。应用和服务常见的做法是：

- 在 `pyproject.toml` 中写明代码直接使用的包和允许的版本范围。
- 用所选工具的锁文件记录所有直接和间接依赖最终选定的准确版本。
- 提交这两个文件，让其他人能够安装同一组版本。

可复用库通常要为使用者保留合理的兼容范围；维护者仍可用锁文件固定自己的测试环境，但发布出去的库不能要求所有使用者采用维护者锁定的整套版本。

`requirements.txt` 既可能是人工维护的直接依赖清单，也可能是工具生成的精确安装快照。不能只看文件名判断它是否等同于锁文件，应查看项目文档和生成方式。

不要手工编辑工具生成的锁文件。应通过对应包管理器更新依赖并重新生成它。

## 7. 直接依赖与传递依赖

如果项目代码直接调用 `httpx`，它就是直接依赖，应该写入项目配置。`httpx` 为了工作而需要的其他包称为传递依赖，也就是项目间接需要的包，通常由包管理器自动处理。

不要因为某个传递依赖“碰巧能导入”就在代码中直接使用它。一旦项目代码直接使用它，就应把它写入项目配置，否则原来的直接依赖调整内部依赖后，项目可能突然失效。

## 8. 安全地更新依赖

更新依赖不是简单追求最新版本。建议按以下顺序操作：

1. 阅读目标包的发布说明和迁移指南。
2. 小范围更新一个包或一组相关包。
3. 查看 `pyproject.toml` 和锁文件具体改了什么。
4. 运行格式化、代码检查（Lint）、测试和关键功能验证。
5. 确认没有意外引入来源不明或名称相似的包。

安装第三方包可能会在电脑上运行这个包提供的代码。应从可信的下载来源获取包，例如官方 Python 包索引 PyPI；同时检查名称和维护者，不要把拼写相近的未知包当作官方包安装。

## 9. 环境变量不是依赖管理

API 密钥、数据库地址和部署配置不属于包依赖，不应写入 `pyproject.toml` 或源码。常见方式是提交不含秘密的 `.env.example`，实际 `.env` 保留在本机且加入 `.gitignore`。

```text
# .env.example
LLM_API_KEY=replace-with-your-key
```

即使文件已加入 `.gitignore`，提交前仍应检查 Git 暂存区中的改动，防止密钥或个人数据进入版本历史。

## 10. 常见错误

### 全局安装后项目可以运行

这掩盖了某些包没有写入项目配置的问题。应创建空环境，再根据项目声明和锁定结果重新安装或同步，而不是依赖电脑上以前装过的包。本仓库对应的验证命令是 `uv sync`，其他项目应使用它们约定的命令。

### 同时维护多份不一致的依赖清单

如果项目同时存在手写 `requirements.txt`、`pyproject.toml` 和多个锁文件，应明确以哪个文件为准，以及其他文件如何生成。不要手工维护多份会逐渐变得不一致的清单。

### 无限制地允许任意版本

未来安装可能获得带有破坏性变化的新版本。应根据项目稳定性要求设置边界并提交锁文件。

### 把标准库当成第三方包安装

`json`、`csv`、`pathlib` 和 `venv` 都属于 Python 标准库，不需要写入依赖列表。安装同名第三方包可能造成混淆或安全风险。

### 把工具命令当成包管理原理

只记住 `uv add` 或 `pip install`，并不能解释依赖写在哪里、谁选择了版本，以及另一台电脑如何复现环境。遇到新项目时，应先回答这三个问题，再执行项目文档给出的命令。

## 11. 练习与验收

先完成一组与工具无关的问题：

1. 找出项目声明直接依赖的位置。
2. 找出项目是否有锁文件或精确版本快照，并说明由谁生成。
3. 区分一个运行时依赖、一个开发依赖和一个传递依赖。
4. 写出从空环境恢复项目时实际使用的命令。

然后基于配套示例完成一次可复现运行。这里使用 `uv` 是因为仓库已经选择它：

1. 查看 `projects/python/pyproject.toml` 中的 Python 版本要求和空依赖列表。
2. 执行 `uv sync`，观察生成的项目环境。
3. 使用 `uv run` 运行程序和标准库测试。
4. 查看 `uv.lock` 如何记录项目自身信息。
5. 删除本地 `.venv` 后再次执行 `uv sync`，确认项目仍能运行。

最后使用两个独立项目做对照练习，不要在现有 `projects/python` 目录中再创建环境。建议使用下面的并列结构：

```text
projects/
├── python/
└── package-management-comparison/
    ├── pip-demo/
    │   ├── .venv/
    │   ├── main.py
    │   └── pyproject.toml
    └── uv-demo/
        ├── .venv/
        ├── pyproject.toml
        ├── src/
        └── uv.lock
```

两个目录各自拥有项目声明和虚拟环境，因此不会争用 `.venv`，也不会让一个工具改动另一个项目的配置。`.venv` 只用于本机，不要提交到 Git。两个项目都应成功导入 `httpx` 并输出其版本；练习比较的是工作流，而不是程序功能。`pip-demo/main.py` 可以使用：

```python
import httpx


def main() -> None:
    print(httpx.__version__)


if __name__ == "__main__":
    main()
```

### pip-demo：手工声明，pip 负责安装

先创建 `pip-demo`，手工准备下面的 `pyproject.toml`。这里由开发者编辑依赖声明，不是由 `pip install` 生成：

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "pip-demo"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.28,<1",
]

[project.scripts]
pip-demo = "main:main"

[dependency-groups]
dev = [
  "pytest>=8,<9",
  "ruff>=0.12,<1",
]

[tool.setuptools]
py-modules = ["main"]
```

这里加入 `[build-system]`，是因为下一步会执行 `python -m pip install .`。命令末尾的 `.` 表示安装当前项目；pip 需要调用构建后端读取项目元数据，并把项目构建成可安装的形式。上面的配置选择 setuptools 作为构建后端：

- `requires = ["setuptools"]` 声明构建过程需要 setuptools。pip 通常会创建隔离的构建环境并自动安装它，不要求开发者预先把 setuptools 装进项目虚拟环境。
- `build-backend = "setuptools.build_meta"` 告诉 pip 应调用 setuptools 提供的哪个构建接口。

这里的“构建”不等于编译 C 或 C++。即使项目只有纯 Python 文件，构建后端仍要确定哪些源码和数据文件属于项目、如何生成项目元数据，以及需要创建哪些命令行入口。本例中的 `[tool.setuptools]` 明确要求把 `main.py` 作为模块包含进安装产物，`[project.scripts]` 则要求安装时生成名为 `pip-demo` 的命令，并在执行该命令时调用 `main.py` 中的 `main()`。

“当前项目”和“当前项目的依赖”是两个不同的安装对象，但不一定由两条命令分别安装。执行 `python -m pip install .` 时，pip 默认会完成两件事：

1. 调用构建后端处理当前项目，并把自己编写的代码、元数据和命令入口安装进虚拟环境。
2. 读取当前项目元数据中的 `[project].dependencies`，解析并安装 `httpx` 等运行时依赖。

因此，本练习不需要再单独执行 `python -m pip install httpx`。安装完成并保持 `pip-demo` 的虚拟环境处于激活状态时，即使当前工作目录不是项目源码目录，shell 仍可以执行 `pip-demo` 命令；这就是安装当前项目的可观察结果。实际项目还可能通过安装自身获得可导入的包、包内数据文件和版本元数据。

`python -m pip install . --no-deps` 可以要求 pip 只安装当前项目而不处理依赖，但这通常用于依赖已经由其他步骤准备好的特殊工作流。如果环境中没有 `httpx`，这样安装后运行本例仍会失败，因此它不适合作为这里的默认命令。

构建系统和运行时依赖是两回事。安装 `httpx` 本身不需要当前项目配置构建后端。执行 `python -m pip install --group dev` 时，pip 会直接读取 `[dependency-groups]`，同样不需要构建当前项目。当练习使用 `pip install .` 安装当前项目时，构建后端才会参与流程；显式写出 `[build-system]` 可以避免依赖工具的默认兼容行为。setuptools 只是可选构建后端之一，并非 `pyproject.toml` 或 pip 强制指定的唯一工具。

下面这些情况不需要仅仅为了让 pip 或其他工具读取 `pyproject.toml` 而添加 `[build-system]`：

- 只用 `python -m pip install httpx` 安装指定的第三方包。
- 只用 `python -m pip install -r requirements.txt` 根据 requirements 文件安装依赖。
- 只用 `python -m pip install --group dev` 读取 `[dependency-groups]`。
- 只把 `pyproject.toml` 用作 Ruff、pytest 等工具的配置文件，由相应工具读取 `[tool.*]`。
- 项目直接从源码目录运行一个或几个脚本，例如执行 `python main.py`，而不执行 `pip install .` 把项目自身安装到虚拟环境。此时 pip 只需根据 requirements 文件或 `[dependency-groups]` 安装第三方依赖，项目自身不需要参与构建。这不表示脚本只能在当前电脑运行；其他人仍可以取得源码、恢复依赖并执行相同命令。

一旦需要执行 `pip install .` 或 `pip install -e .`、构建 wheel 或源码发行包，或者把项目发布给别人安装，构建后端就会参与流程，此时应在 `[build-system]` 中明确声明项目采用的后端。不要为了“让 pip 认识 pyproject.toml”随意添加一个实际不会使用的构建后端。

然后创建环境，安装当前项目、运行时依赖和开发依赖：

```shell
cd pip-demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m pip install --group dev
python main.py
pip-demo
```

第一条安装命令已经同时安装当前项目及其运行时依赖，`python -m pip install --group dev` 则额外安装不属于运行时依赖的 pytest 和 Ruff。`python main.py` 是直接运行源码，`pip-demo` 则使用安装当前项目时生成的命令入口。两条运行命令应输出相同的 `httpx` 版本。

激活虚拟环境会把 `.venv/bin` 加到当前 shell 的 `PATH` 前面，切换工作目录不会撤销这项修改。可以在环境仍然激活时执行：

```shell
cd ..
pip-demo
cd pip-demo
```

此时 `pip-demo` 来自虚拟环境，而不依赖 shell 当前位于源码目录。新开一个没有激活该环境的 shell，或者执行 `deactivate` 后，通常不能再直接找到该命令；这时必须重新激活环境，或显式执行 `.venv/bin/pip-demo` 的正确路径。Windows 的命令目录是 `.venv\Scripts`，原理相同。

接着安装一个没有写入项目声明的包，并确认它确实进入了当前环境：

```shell
python -m pip install rich
python -m pip show rich
python -m pip uninstall rich
```

观察安装 `rich` 后 `pyproject.toml` 没有变化。卸载命令默认会要求确认；确认后，环境中便不会留下这项未声明依赖。

重建环境前先执行 `python -m pip freeze` 并记录输出，然后执行 `deactivate`，再删除并重新创建 `.venv`。重新激活环境后，只根据 `pyproject.toml` 安装依赖，并再次运行 `python -m pip freeze`。

两次输出可能相同，也可能不同，不要求为了练习制造版本差异。需要判断的是：`pyproject.toml` 只声明了允许的版本范围，而且项目没有记录本次解析结果，因此无法保证以后仍安装完全相同的版本。如果两次输出相同，只能说明当前包索引和解析条件得出了相同结果；这不等于项目已经具备精确复现能力。如果输出不同，则找出发生变化的直接依赖或传递依赖。

`pip install --group` 需要 pip 25.1 或更高版本。如果环境中的 pip 不支持该选项，可以把开发依赖放入单独的 `requirements-dev.txt`，再执行 `python -m pip install -r requirements-dev.txt`。不要为了完成练习而把开发工具混入运行时依赖。

完成 `pip-demo` 后退出虚拟环境并返回两个示例的共同父目录，再继续 `uv-demo`：

```shell
deactivate
cd ..
```

### uv-demo：命令同时维护声明和环境

先创建并进入空的 `uv-demo` 目录，再显式使用 `--package` 初始化可安装项目。这样不依赖不同 uv 版本对项目模板的默认选择：

```shell
cd uv-demo
uv init --package --no-workspace
uv add httpx
uv add pytest ruff --dev
uv run uv-demo
uv run python -c "import httpx; print(httpx.__version__)"
```

uv 并没有绕过 Python 构建系统。`--package` 表示项目自身需要被构建并安装，`uv init` 会自动在 `pyproject.toml` 中生成 `[build-system]`；随后 `uv sync` 或 `uv run` 会调用该后端，并把当前项目安装到项目环境。与 `pip-demo` 的区别是：练习者在 `pip-demo` 中手工选择并声明 setuptools，而 uv 初始化命令替 `uv-demo` 生成了构建配置。

`uv add` 修改依赖声明、解析版本和同步第三方依赖的能力本身不依赖项目构建后端。如果明确创建不需要安装自身的脚本项目，可以改用 `uv init --no-package --no-workspace`；该模式不会生成 `[build-system]`，`uv` 只同步项目依赖，并直接用 `uv run python main.py` 执行源码。这里使用 `--package`，是为了让两个对照项目都安装自身，避免把“是否需要构建系统”误解成 pip 与 uv 的差异。

然后比较两个项目的 `pyproject.toml`，确认它们都有 `[build-system]`，直接依赖和开发依赖表达的是相同需求；再观察只有 `uv-demo` 由项目管理工具自动生成了 `uv.lock`。

最后删除 `uv-demo/.venv` 并执行 `uv sync`，观察环境如何根据声明和锁文件恢复。

技术上允许在同一目录创建多个不同名称的虚拟环境，例如 `.venv-pip` 和 `.venv-uv`，但不建议在这项练习中这样做。工具、编辑器和 shell 可能选择不同解释器；`uv` 项目命令默认管理项目根目录中的 `.venv`，也不会默认采用另一个已经激活的环境。分目录能让配置、锁文件和环境的归属一目了然。

完成后，说明 `pip install` 与 `uv add` 在“修改项目声明”方面有什么差异，并指出两个工作流分别如何完成声明、解析、安装、运行和环境重建。

完成标准：面对采用任一种常见工具的项目，都能找到依赖声明和锁定方式，并按 README 在空环境中恢复项目；同时能说明本仓库为什么需要匹配的 Python 与 `uv`。

完成本专题后，回到 [Python 工程基础](index.md)检查整体完成标准。

## 延伸阅读

- [uv 项目依赖管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [uv 锁定与同步](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Python pyproject.toml 指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Python 安装包指南](https://packaging.python.org/en/latest/tutorials/installing-packages/)
- [pip 用户指南](https://pip.pypa.io/en/stable/user_guide/)
