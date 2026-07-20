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
