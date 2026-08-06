# AI Demo

这个仓库同时保存人工智能学习笔记和可运行的代码项目，两类内容相互关联但保持独立。

## 仓库入口

- [学习笔记](notes/index.md)：Roadmap、概念整理、实验记录和参考资料。
- [代码项目](projects/README.md)：RAG、Agent、模型推理与 AI Infra 实践项目。

## 目录约定

```text
AI-demo/
├── README.md
├── notes/                  # Markdown 知识库，可单独作为笔记软件的库目录
│   ├── index.md            # 笔记入口
│   └── roadmap.md          # 总体学习路线
├── scripts/                # 仓库级开发辅助脚本
└── projects/               # 独立、可运行的代码项目
    └── README.md           # 项目目录约定
```

知识说明放在 `notes/`，程序源码、测试、依赖和部署配置放在 `projects/`。笔记需要引用代码时，使用相对链接指向具体项目；代码项目则在自己的 README 中链接相关笔记。

## Markdown 兼容原则

- 使用标准 Markdown 相对链接，不依赖 Wikilink。
- 使用简单 YAML Front Matter 保存标题、类型、领域和状态。
- 图片和图表使用相对路径，避免本机绝对路径。
- 核心导航不依赖 Obsidian、Joplin 或其他软件的插件。

具体写作规则和格式检查命令见 [Markdown 规范](docs/markdown-style-guide.md)。

```shell
npm run format
npm run lint
```

## 切换 VS Code Python 环境

仓库包含一个一键切换 VS Code Python 项目的脚本。它会查找目标项目的 `.venv`，把 Python Environments 的项目和搜索路径切换为该目标，并无损更新工作区设置及已有 Python 调试配置。Python Environments 扩展会实时读取这些设置，因此通常不需要重新加载窗口；当扩展此前已为工作区选中过其他环境时（多 Python 项目工作区中常见），脚本会在 macOS 上自动执行 `Python: Select Interpreter` 命令把选中对齐到目标环境，无法自动化时则会输出手动指引。

首次使用时，通过脚本自身安装全局命令：

```shell
./scripts/use-venv.zsh --install
```

安装操作会将独立脚本复制到 `~/.local/bin/use-venv`。全局命令不依赖当前仓库的路径，因此原仓库移动或删除后仍可用于其他本地 VS Code 工作区；再次安装会安全更新由本脚本管理的副本，不会覆盖同名的其他文件。随后可在任意目录运行：

```shell
use-venv projects/engineering-foundations
```

也可以同时指定目标项目和它所属的本地 VS Code 工作区：

```shell
use-venv /path/to/workspace/project --workspace /path/to/workspace
```

这里的两个路径作用不同：第一个路径指定拥有 `.venv` 的 Python 项目，`--workspace` 指定需要修改 `.vscode/settings.json` 以及已有 `.vscode/launch.json` 的 VS Code 工作区根目录。这主要用于以下情况：

- VS Code 打开的是 monorepo 根目录，而 Python 项目和 `.venv` 位于其中的子目录。
- 项目嵌套在另一个 Git 仓库中，自动向上查找可能选择错误的仓库根目录。
- 项目路径上存在多个 `.vscode/settings.json`，需要明确指定实际打开的工作区。
- 从工作区之外的任意目录调用全局命令，无法依赖当前目录推断工作区。

例如 VS Code 打开 `/path/to/workspace`，目标环境位于 `/path/to/workspace/projects/api/.venv` 时，使用：

```shell
use-venv /path/to/workspace/projects/api --workspace /path/to/workspace
```

通常只传项目路径即可，脚本会自动向上寻找工作区；工作区根目录与项目目录相同或自动推断正确时，不需要 `--workspace`。

在目标项目内部运行时可以省略路径：

```shell
cd projects/engineering-foundations
use-venv
```

脚本不会写入 `python.defaultInterpreterPath`（该设置只在工作区从未选择过解释器时生效）。`python-envs.pythonProjects` 与 `python-envs.workspaceSearchPaths` 中只保留目标项目与目标 `.venv`，使 Python Environments 扩展重新发现目标环境；`python.terminal.activateEnvironment` 会让随后新建的终端自动激活它，已有终端不会被追溯修改。扩展自己存储的“选中环境”独立于配置文件：若此前选中过其他环境，脚本会检测出来，并通过 `Python: Select Interpreter` 命令重新对齐；该步骤只读扩展存储用于验证，不修改任何配置文件。

脚本主体位于 `scripts/use-venv.zsh`，其中内嵌的 Python 代码只对需要变更的 JSONC 配置值进行局部编辑，保留其他配置、注释和原有排版；已有 `launch.json` 中的 Python/debugpy 配置会同步更新 `python`、`cwd` 及已经存在的相关环境变量，其他类型的调试配置保持不变。两个配置文件按事务处理：后续步骤失败时会恢复脚本执行前的原始内容；若文件在脚本写入后又被其他程序修改，则不会强行覆盖，而会保留事务备份并报告路径。

通常无需重新加载。若确实需要，可显式追加 `--reload`，让脚本在 macOS 上通过 VS Code 的 View 菜单打开命令面板，并重新加载当前处于前台的 VS Code 窗口。脚本会验证英文 `Developer: Reload Window` 或中文 `开发人员: 重新加载窗口` 命令，只有匹配成功才执行；自动化失败时配置修改会回滚。`--workspace` 只指定配置文件所在目录，不负责选择某个已打开的窗口，因此打开多个 VS Code 窗口时，应先把目标窗口切到前台。`--no-reload` 仍作为兼容参数保留，但现在已经是默认行为。已有终端不会被追溯切换，配置生效后需新建终端。不再需要全局命令时，可以安全卸载：

```shell
use-venv --uninstall
```
