# 代码项目

该目录用于保存与学习路线配套的可运行代码。每个项目使用独立子目录，并自行管理源码、测试、依赖和部署配置。

## 推荐结构

```text
projects/
└── rag-knowledge-base/
    ├── README.md
    ├── .env.example
    ├── src/
    ├── tests/
    ├── scripts/
    ├── docker-compose.yml
    └── <依赖与构建清单>
```

## 项目约定

- 一个子目录对应一个可以独立运行和验证的项目。
- 仓库不统一限定项目语言；每个项目根据需求选择技术栈并独立管理依赖。
- 每个项目必须有 README，说明目标、架构、运行方法、测试方法和评测结果。
- 密钥只通过环境变量或本地配置注入，仓库中只保留不含真实值的 `.env.example`。
- 项目产生的数据集、模型权重、向量索引和构建产物不放入 `notes/`。
- 重要实验结论整理到笔记中；完整日志和运行产物保留在对应项目范围内。
- 项目 README 使用相对链接关联相关学习笔记，例如 [总体学习路线](../notes/roadmap.md)。

依赖管理随项目语言确定：

- Python 项目使用 `pyproject.toml` 和 `uv.lock`，通过 `uv sync` 安装、`uv run` 执行。
- `package-management-comparison/pip-demo` 是教学例外，故意不提交锁文件，用于与 uv 锁定工作流对照。
- Node.js 项目使用 `package.json` 和所选包管理器对应的锁文件。
- Go 项目使用 `go.mod` 和 `go.sum`。
- Rust 项目使用 `Cargo.toml` 和 `Cargo.lock`。

项目必须提交可复现的依赖清单和锁文件，不能依赖开发者机器上碰巧存在的全局软件。

## 已有项目

| 项目                                                                     | 目标                                             | 状态   |
| ------------------------------------------------------------------------ | ------------------------------------------------ | ------ |
| [python](python/README.md)                                               | 统一保存 Python 课程的可运行示例、测试和样本数据 | 可运行 |
| [engineering-foundations](engineering-foundations/README.md)             | 演示可定位日志、基础测试和日志级别交互实验       | 可运行 |
| [package-management-comparison](package-management-comparison/README.md) | 对照 pip 与 uv 的依赖管理和环境恢复工作流        | 可运行 |

## 计划中的项目

| 项目                  | 目标                                     | 状态   |
| --------------------- | ---------------------------------------- | ------ |
| `rag-knowledge-base`  | 构建带引用、评测和可观测性的中文知识库   | 计划中 |
| `repository-agent`    | 实现有工具权限与人工审批的代码仓库助手   | 计划中 |
| `inference-benchmark` | 比较模型服务的延迟、吞吐、显存与量化配置 | 计划中 |

项目目录在真正开始编码时再创建，避免保留没有实现内容的空工程。
