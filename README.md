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

## 切换 VS Code 与 Cursor 的 Python 环境

仓库包含一个切换 VS Code 或 Cursor Python 项目的脚本。它会查找目标项目的 `.venv`，把共享的 Python Environments 项目和搜索路径切换为该目标，并更新工作区设置及已有 Python 调试配置。两种编辑器分别安装 Python 和 Python Environments 扩展后，可以读取同一份仓库配置，但各自保存的解释器选择相互独立。脚本在 macOS 上使用 VS Code 的 `Python: Select Interpreter` 命令或 Cursor 辅助扩展的环境 API 对齐选择，并回读结果，不直接改写扩展私有存储。

首次使用时，通过脚本自身安装全局命令：

```shell
./scripts/use-venv.zsh --install
```

安装操作会将独立脚本复制到 `~/.local/bin/use-venv`。全局命令不依赖当前仓库的路径，因此原仓库移动或删除后仍可用于其他本地 VS Code 或 Cursor 工作区；脚本更新后须再次执行安装命令，才会更新全局副本。安装不会覆盖同名的非托管文件。随后可在任意目录运行：

```shell
use-venv projects/engineering-foundations
```

默认只对齐 VS Code，保留原有用法。通过 `--editor` 指定 Cursor，或依次对齐两边：

```shell
use-venv projects/llm-terminal-assistant --editor cursor
use-venv projects/llm-terminal-assistant --editor both
```

只使用一个编辑器时，不需要打开另一个。目标编辑器未运行时，脚本只更新共享配置并报告该编辑器的选择仍待同步，不会自动启动它；打开目标工作区后可重新执行命令。`both` 会分别处理正在运行的编辑器，并逐一报告未运行的编辑器，不能把配置已更新理解成两边的解释器已经全部选中。VS Code 的目标工作区窗口需要处于前台；Cursor 由辅助扩展按完整路径识别工作区，不要求前台焦点。两者都需要事先打开目标工作区。

也可以同时指定目标项目和它所属的本地工作区：

```shell
use-venv /path/to/workspace/project --workspace /path/to/workspace
```

这里的两个路径作用不同：第一个路径指定拥有 `.venv` 的 Python 项目，`--workspace` 指定需要修改 `.vscode/settings.json` 以及已有 `.vscode/launch.json` 的工作区根目录。这主要用于以下情况：

- 编辑器打开的是 monorepo 根目录，而 Python 项目和 `.venv` 位于其中的子目录。
- 项目嵌套在另一个 Git 仓库中，自动向上查找可能选择错误的仓库根目录。
- 项目路径上存在多个 `.vscode/settings.json`，需要明确指定实际打开的工作区。
- 从工作区之外的任意目录调用全局命令，无法依赖当前目录推断工作区。

例如编辑器打开 `/path/to/workspace`，目标环境位于 `/path/to/workspace/projects/api/.venv` 时，使用：

```shell
use-venv /path/to/workspace/projects/api --workspace /path/to/workspace
```

通常只传项目路径即可，脚本会自动向上寻找工作区；工作区根目录与项目目录相同或自动推断正确时，不需要 `--workspace`。

在目标项目内部运行时可以省略路径：

```shell
cd projects/engineering-foundations
use-venv
```

脚本不会写入 `python.defaultInterpreterPath`（该设置只在工作区从未选择过解释器时生效）。`python-envs.pythonProjects` 与 `python-envs.workspaceSearchPaths` 中只保留目标项目与目标 `.venv`，使 Python Environments 扩展重新发现目标环境；`python.analysis.extraPaths` 与 `cursorpyright.analysis.extraPaths` 同步指向目标源码目录。`python.terminal.activateEnvironment` 会让随后新建的终端自动激活所选环境，已有终端不会被追溯修改。VS Code 保留读取选择状态和调用选择命令的流程；Cursor 通过 Python Environments 的环境 API 选择目标并回读结果。不能仅因没有找到选择状态就认定成功。

选择 Cursor 或 `both` 时，脚本先检查 Python 环境扫描工具 `pet` 能否运行并发现目标解释器。新终端由辅助扩展使用稳定的终端接口激活，普通切换不再检查或补写 `terminalDataWriteEvent` 授权，因此 Cursor 更新覆盖应用文件不会清除这条激活路径。扫描工具有问题时，仍须显式授权扩展包修复：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --repair-cursor-envs
```

`--repair-cursor-envs` 只适用于 macOS 上的 Cursor 或 `both`。工具缺失或无法启动时，它会读取 Cursor 当前安装的 Python Environments 版本，选择与本机架构匹配的同版本平台包。脚本优先检查 Cursor 和 VS Code 的扩展包缓存；找不到合适缓存时，从 Microsoft Visual Studio Marketplace 获取对应 VSIX，并核对发布者、扩展名称、版本、平台以及 `pet` 文件后，交给 Cursor CLI 安装。若没有对应平台包或安装失败，脚本会明确停止，不使用其他版本替代。

安装会将完整扩展包放进 Cursor 自己的扩展目录，不创建指向 VS Code 扩展目录的链接，也不保留对缓存文件的运行依赖。工具已经可用时，即使传入修复选项也不会重复安装。实际替换扩展包后，脚本先写入目标工作区配置，再通过本地辅助扩展调用窗口重载，并在最多 40 秒内等待目标工作区的新扩展实例连接。随后最多等待 30 秒，通过本次重载后产生的日志确认 Python Environments 激活和目标解释器发现。解释器选择使用该扩展公开的环境 API，并回读结果；选择失败或超时会停止切换。VS Code 的选择流程保持不变。

替换前，脚本在 `~/Library/Application Support/use-venv/transactions/` 中保存可重新安装的原扩展包。修复或后续切换失败时，除了回滚共享配置，还会重新安装原包、核对版本、平台及入口文件，并再次完整重载运行中的 Cursor 窗口；恢复原包时只等待扩展激活，不要求原包具备修复后的扫描工具。若恢复失败或检测到其他程序更新了扩展，会保留备份并报告路径。全部切换成功并验证后，脚本删除自己创建的备份。Cursor 未运行而无法验证切换时，也不会保留尚未验证的替换。Cursor 扩展目录中的旧版本由 Cursor 自己管理。脚本不改变扩展自动更新策略；将来更新若再次导致工具缺失，可以重新运行带修复选项的命令。VS Code 单独切换不执行这些检查或修复。

验证新终端时，辅助扩展通过终端 API 创建专用终端，向这个终端对象发送只读探测命令，检查 shell PID、`VIRTUAL_ENV` 和 `python` 搜索路径。探测命令本身不执行激活，也不注入虚拟环境变量；新终端经过与用户终端相同的自动激活处理，只有实际环境和解释器路径符合预期才判定成功。成功或失败后都会关闭专用终端，并确认关闭事件。终端操作有超时限制；无法确认关闭时会保留探测文件并报告错误。这个过程不使用菜单、命令面板、模拟按键或临时编辑器预览页。

在脚本触发的 Cursor 窗口重载或完整重启前，脚本会记录目标项目的旧 `unittest` 测试发现进程，包括 PID、启动时间、命令及其 Cursor 扩展宿主。操作成功或失败后均执行退出检查：先等待任务自行结束，仅在原宿主已退出且旧任务成为孤儿进程时，才向仍与记录匹配的 PID 发送终止信号；等待后仍未退出才强制结束，并再次验证。三个等待阶段分别最多 2 秒，每次进程查询也有独立超时。新启动的发现任务、其他项目或编辑器的任务、宿主仍存活的任务，以及身份已变化的 PID 均保留。无法确认退出时报告具体 PID；已有操作错误时保留该错误，同时报告清理问题。此机制针对脚本自身的重载和重启，不持续监控手动关闭或扩展崩溃，也不修改自动测试发现设置。

启动 Cursor 和调用其命令行时，颜色控制变量遵循桌面环境设置，避免继承自动化工具用于自身输出的 `NO_COLOR=1`、`TERM=dumb` 等值，影响编辑器及新终端的显示。未配置的桌面变量不会作为空字符串传入。

旧的 API 授权修复及其回滚入口已移除；终端激活由辅助扩展接管，不再修改 Cursor 的 `product.json`。

脚本的全局状态变量统一使用 `USE_VENV_` 前缀，Cursor 专属变量使用 `USE_VENV_CURSOR_`。共享配置备份和扩展包备份由脚本管理，默认放在 `~/Library/Application Support/use-venv/transactions/`；新建状态根目录使用仅当前用户可访问的权限。共享配置事务还记录工作区及配置文件路径，便于识别保留下来的恢复数据。可通过 `USE_VENV_STATE_DIRECTORY` 指定绝对路径，用于测试或隔离运行状态，不需要修改仓库配置。

脚本仍兼容旧的 `VSCODE_VENV_CURSOR_EXTENSION_DIRECTORY`、`VSCODE_VENV_CURSOR_LOG_DIRECTORY` 和 `VSCODE_VENV_EDITOR_STORAGE_DIRECTORY` 环境变量；对应新名称分别为 `USE_VENV_CURSOR_EXTENSION_DIRECTORY`、`USE_VENV_CURSOR_LOG_DIRECTORY` 和 `USE_VENV_EDITOR_STORAGE_DIRECTORY`。新旧名称同时设置时，新名称优先。

处理 Cursor 前，脚本会检查当前工作区旧 `.agent-tmp/` 中的 `cursor-envs-transaction.*` 修复记录，将可识别的完整记录迁入新的状态根目录；不会迁移其他 Agent 临时文件。迁移目标已经存在、数据不完整或包含符号链接时，会停止并保留相关数据供处理，不覆盖现存备份。用户正常运行脚本不再向 `.agent-tmp/` 写入事务或探测文件。

脚本主体位于 `scripts/use-venv.zsh`，其中负责配置更新的 Python 代码只对需要变更的 JSONC 配置值进行局部编辑，保留其他配置、注释和原有排版；已有 `launch.json` 中的 Python/debugpy 配置会同步更新 `python`、`cwd` 及已经存在的相关环境变量，其他类型的调试配置保持不变。两个配置文件按事务处理：后续步骤失败时会恢复脚本执行前的原始内容；若文件在脚本写入后又被其他程序修改，则不会强行覆盖，而会保留事务备份并报告路径。配置文件回滚不会撤销编辑器中已经完成的解释器选择；使用 `both` 时，若第二个编辑器失败，应按错误提示核对两边的状态。

Cursor 的自动化由仓库维护的 `ai-demo-local.use-venv-helper` 辅助扩展执行。它不是微软官方扩展，也不需要上架市场；扩展包随独立脚本内嵌，脚本在扫描工具检查允许继续后按需安装或更新。首次安装而当前窗口尚未加载扩展时，需要从 Cursor 外部终端运行，脚本会正常退出并重新打开 Cursor；遇到保存确认或退出超时会停止，不强制退出。已有辅助扩展可响应时，更新通过窗口重载加载。如果扩展已安装却无法连接，脚本会限时等待并报错，不退回界面自动化。

辅助扩展会在 Cursor 启动、现有 `pylint.interpreter` 配置变化以及显式切换环境时，同步 Python 扩展的工作区解释器，并回读语言服务所使用的接口确认结果。它复用脚本已维护的解释器路径，不增加 `python.pythonPath` 配置；工作区解释器选择保存在 Cursor 的扩展状态中。扩展只在 Cursor 宿主中启动。更新后首次使用仍需通过脚本安装新版辅助扩展。

辅助扩展在本地、单工作区且已配置有效虚拟环境时自动接管终端激活：先保存 Cursor 用户级 `python-envs.terminal.autoActivationType` 原值，再将其设为 `off`，避免 Python Environments 重复激活。此设置不写入仓库共享配置，也不修改 VS Code 用户设置。对新建的 zsh/bash 交互终端，扩展等待 Shell Integration 就绪，核对终端目录属于目标项目后执行激活；任务终端、其他项目和已有终端不处理，等待超过 10 秒时不盲目发送命令。此方案目前按单工作区使用，不承诺其他 Cursor 工作区也自动激活。

如需退出接管，在 Cursor 命令面板运行 `use-venv: Restore Python Terminal Activation`。命令停止接管并恢复保存的用户设置；原来没有该设置时删除这一项。如果用户已将其改为其他值，则保留用户的新值。退出状态会持久保存，重载不会自动再次接管。卸载辅助扩展前应先执行此恢复命令。

需要强制重新安装内嵌的辅助扩展并使其生效时，先打开目标 Cursor 工作区，再运行：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --reinstall-cursor-helper
```

此选项跳过版本匹配的快捷路径，强制安装并等待重载后的新实例握手。它也适用于已安装但无法连接的辅助扩展；这种情况下需要从 Cursor 外部终端运行，脚本会正常重启 Cursor。此选项支持 `cursor` 或 `both`。

辅助扩展只监听本机回环地址，使用保存在用户私有目录中的随机令牌验证请求，并核对完整工作区路径；同一工作区存在多个可响应窗口时拒绝操作。连接信息和终端探测文件位于 `~/Library/Application Support/use-venv/helper/`。重载完成以新实例握手为准，不依赖窗口标题或前台焦点。源码位于 `scripts/cursor-helper/`；修改后运行 `python3 scripts/cursor-helper/build.py` 更新脚本中的内嵌包，再重新安装全局命令。

通常无需主动重新加载。显式追加 `--reload` 时，Cursor 通过辅助扩展重载目标工作区；VS Code 保持通过 View 菜单打开命令面板、匹配中英文重载命令的原有流程。修复流程已经重载过 Cursor 时，不重复重载。未运行的编辑器仍报告待同步，不因 `--reload` 启动。`--no-reload` 作为兼容参数保留。已有终端不会被追溯切换，配置生效后需新建终端。不再需要全局命令时，可以卸载；本地辅助扩展可另用 `cursor --uninstall-extension ai-demo-local.use-venv-helper` 卸载：

```shell
use-venv --uninstall
```

脚本的离线回归测试不操作真实编辑器或解释器选择，可在仓库根目录执行：

```shell
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
node --test scripts/cursor-helper/extension.test.js
npm run lint:scripts
```
