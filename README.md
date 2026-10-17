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

选择 Cursor 或 `both` 时，脚本始终先做两项只读检查，不要求传入修复选项。一项检查 Python 环境扫描工具 `pet` 能否运行并发现目标解释器，按扩展的实际顺序查找 Python Environments 自带的工具及 Python 扩展中的备用工具；另一项检查扩展请求的 `terminalDataWriteEvent` API 在 Cursor 中是否可用、是否已获授权。扩展未请求该 API 时，授权检查不作为阻塞条件。两项检查都会执行并报告结果。

修复选项只授权修改对应问题。未授权修复的问题仍然存在时，脚本在安装扩展或修改配置前停止，即使已经授权修复另一项也一样。两项都有问题时，需要同时传入两个修复选项。只需授权扩展包修复时，命令如下：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --repair-cursor-envs
```

`--repair-cursor-envs` 只适用于 macOS 上的 Cursor 或 `both`。工具缺失或无法启动时，它会读取 Cursor 当前安装的 Python Environments 版本，选择与本机架构匹配的同版本平台包。脚本优先检查 Cursor 和 VS Code 的扩展包缓存；找不到合适缓存时，从 Microsoft Visual Studio Marketplace 获取对应 VSIX，并核对发布者、扩展名称、版本、平台以及 `pet` 文件后，交给 Cursor CLI 安装。若没有对应平台包或安装失败，脚本会明确停止，不使用其他版本替代。

安装会将完整扩展包放进 Cursor 自己的扩展目录，不创建指向 VS Code 扩展目录的链接，也不保留对缓存文件的运行依赖。工具已经可用时，即使传入修复选项也不会重复安装。实际替换扩展包后，脚本先写入目标工作区配置，再通过本地辅助扩展调用窗口重载，并在最多 40 秒内等待目标工作区的新扩展实例连接。随后最多等待 30 秒，通过本次重载后产生的日志确认 Python Environments 激活和目标解释器发现。解释器选择使用该扩展公开的环境 API，并回读结果；选择失败或超时会停止切换。VS Code 的选择流程保持不变。

替换前，脚本在 `~/Library/Application Support/use-venv/transactions/` 中保存可重新安装的原扩展包。修复或后续切换失败时，除了回滚共享配置，还会重新安装原包、核对版本、平台及入口文件，并再次完整重载运行中的 Cursor 窗口；恢复原包时只等待扩展激活，不要求原包具备修复后的扫描工具。若恢复失败或检测到其他程序更新了扩展，会保留备份并报告路径。全部切换成功并验证后，脚本删除自己创建的备份。Cursor 未运行而无法验证切换时，也不会保留尚未验证的替换。Cursor 扩展目录中的旧版本由 Cursor 自己管理。脚本不改变扩展自动更新策略；将来更新若再次导致工具缺失，可以重新运行带修复选项的命令。VS Code 单独切换不执行这些检查或修复。

如果 API 检查发现扩展缺少 `terminalDataWriteEvent` 授权，而扫描工具检查已通过，可以授权应用兼容修复。先打开目标 Cursor 工作区，再从 **Cursor 以外的终端** 运行：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --repair-cursor-api
```

此选项允许修复检查发现的授权缺失。只有确实缺少授权时，才备份并局部修改 Cursor 的 `product.json`，随后完整退出、重新启动 Cursor；窗口重载不能替代此次重启。已有授权时不重复修改或重启。此操作只支持 macOS；需要执行 API 修复时，应从 Cursor 以外的终端运行，因为脚本会重启 Cursor。

两项检查都发现问题时，可以同时授权修复：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --repair-cursor-envs --repair-cursor-api
```

脚本先检查，再修复扫描工具、更新工作区并选择环境，最后在需要时修复 API 授权及验证新终端。两项修复共用本次切换的成功边界。后续步骤失败时，共享配置、本次替换的扩展包和本次新增的 API 授权都会尝试回滚；已有的正常状态不会因另一项失败而撤销。只有全部步骤通过后才清理本次修复备份。

验证新终端时，辅助扩展通过终端 API 创建专用终端，向这个终端对象发送只读探测命令，检查 shell PID、`VIRTUAL_ENV` 和 `python` 搜索路径。它不主动执行环境激活命令，也不向终端注入虚拟环境变量；只有实际环境和解释器路径符合预期才判定成功。成功或失败后都会关闭专用终端，并确认关闭事件。终端操作有超时限制；无法确认关闭时会保留探测文件并报告错误。这个过程不使用菜单、命令面板、模拟按键或临时编辑器预览页。

在脚本触发的 Cursor 窗口重载或完整重启前，脚本会记录目标项目的旧 `unittest` 测试发现进程，包括 PID、启动时间、命令及其 Cursor 扩展宿主。操作成功或失败后均执行退出检查：先等待任务自行结束，仅在原宿主已退出且旧任务成为孤儿进程时，才向仍与记录匹配的 PID 发送终止信号；等待后仍未退出才强制结束，并再次验证。三个等待阶段分别最多 2 秒，每次进程查询也有独立超时。新启动的发现任务、其他项目或编辑器的任务、宿主仍存活的任务，以及身份已变化的 PID 均保留。无法确认退出时报告具体 PID；已有操作错误时保留该错误，同时报告清理问题。此机制针对脚本自身的重载和重启，不持续监控手动关闭或扩展崩溃，也不修改自动测试发现设置。

启动 Cursor 和调用其命令行时，颜色控制变量遵循桌面环境设置，避免继承自动化工具用于自身输出的 `NO_COLOR=1`、`TERM=dumb` 等值，影响编辑器及新终端的显示。未配置的桌面变量不会作为空字符串传入。

如果 macOS 拒绝写入应用文件，需要为运行命令的应用授予“隐私与安全性 → App 管理”权限。验证失败时，脚本恢复原文件并再次重启 Cursor；恢复失败或文件被其他进程修改时，会保留 `~/Library/Application Support/use-venv/transactions/cursor-api-repair/` 备份。中断后可以从外部终端运行以下命令恢复尚未完成的事务：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --rollback-cursor-api
```

成功修复后备份已删除，该回滚选项不再适用。Cursor 更新可能替换应用配置；再次出现同一 API 授权错误时，可以重新运行检查和修复。此选项不修改 VS Code，也不保证修复其他原因造成的终端激活失败。

脚本的全局状态变量统一使用 `USE_VENV_` 前缀，Cursor 专属变量使用 `USE_VENV_CURSOR_`。共享配置备份、扩展包备份和 API 修复状态由脚本管理，默认放在 `~/Library/Application Support/use-venv/transactions/`；新建状态根目录使用仅当前用户可访问的权限。共享配置事务还记录工作区及配置文件路径，便于识别保留下来的恢复数据。可通过 `USE_VENV_STATE_DIRECTORY` 指定绝对路径，用于测试或隔离运行状态，不需要修改仓库配置。

脚本仍兼容旧的 `VSCODE_VENV_CURSOR_EXTENSION_DIRECTORY`、`VSCODE_VENV_CURSOR_LOG_DIRECTORY` 和 `VSCODE_VENV_EDITOR_STORAGE_DIRECTORY` 环境变量；对应新名称分别为 `USE_VENV_CURSOR_EXTENSION_DIRECTORY`、`USE_VENV_CURSOR_LOG_DIRECTORY` 和 `USE_VENV_EDITOR_STORAGE_DIRECTORY`。新旧名称同时设置时，新名称优先。

处理 Cursor 前，脚本会检查当前工作区旧 `.agent-tmp/` 中的 `cursor-api-repair/` 和 `cursor-envs-transaction.*` 修复记录，将可识别的完整记录迁入新的状态根目录；不会迁移其他 Agent 临时文件。旧 API 恢复记录迁移后仍可使用 `--rollback-cursor-api`。迁移目标已经存在、数据不完整或包含符号链接时，会停止并保留相关数据供处理，不覆盖现存备份。用户正常运行脚本不再向 `.agent-tmp/` 写入事务或探测文件。

脚本主体位于 `scripts/use-venv.zsh`，其中负责配置更新的 Python 代码只对需要变更的 JSONC 配置值进行局部编辑，保留其他配置、注释和原有排版；已有 `launch.json` 中的 Python/debugpy 配置会同步更新 `python`、`cwd` 及已经存在的相关环境变量，其他类型的调试配置保持不变。两个配置文件按事务处理：后续步骤失败时会恢复脚本执行前的原始内容；若文件在脚本写入后又被其他程序修改，则不会强行覆盖，而会保留事务备份并报告路径。配置文件回滚不会撤销编辑器中已经完成的解释器选择；使用 `both` 时，若第二个编辑器失败，应按错误提示核对两边的状态。

Cursor 的自动化由仓库维护的 `ai-demo-local.use-venv-helper` 辅助扩展执行。它不是微软官方扩展，也不需要上架市场；扩展包随独立脚本内嵌，脚本在两项检查允许继续后按需安装或更新。首次安装而当前窗口尚未加载扩展时，需要从 Cursor 外部终端运行，脚本会正常退出并重新打开 Cursor；遇到保存确认或退出超时会停止，不强制退出。已有辅助扩展可响应时，更新通过窗口重载加载。如果扩展已安装却无法连接，脚本会限时等待并报错，不退回界面自动化。

辅助扩展会在 Cursor 启动、现有 `pylint.interpreter` 配置变化以及显式切换环境时，同步 Python 扩展的工作区解释器，并回读语言服务所使用的接口确认结果。它复用脚本已维护的解释器路径，不增加 `python.pythonPath` 配置；工作区解释器选择保存在 Cursor 的扩展状态中。扩展只在 Cursor 宿主中启动。更新后首次使用仍需通过脚本安装新版辅助扩展。

需要强制重新安装内嵌的辅助扩展并使其生效时，先打开目标 Cursor 工作区，再运行：

```shell
use-venv projects/llm-terminal-assistant --editor cursor --reinstall-cursor-helper
```

此选项跳过版本匹配的快捷路径，强制安装并等待重载后的新实例握手。它也适用于已安装但无法连接的辅助扩展；这种情况下需要从 Cursor 外部终端运行，脚本会正常重启 Cursor。此选项支持 `cursor` 或 `both`，不能与 API 回滚同时使用。

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
