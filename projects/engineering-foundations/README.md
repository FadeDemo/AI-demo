# 工程基础示例

本项目配套[日志基础](../../notes/engineering/logging.md)和[基础测试](../../notes/engineering/basic-testing.md)课程。它实现一个小型内存文档搜索模块，用同一段业务代码演示日志级别、结构化上下文、请求 ID、pytest 参数化、fixture、异常与日志断言。

课程的必需验收项和不影响完成结果的可选增强统一定义在[通用工程基础课程入口](../../notes/engineering/index.md)中。项目 README 只说明运行方式，不额外增加验收条件。

## 环境要求

- Python 3.11 或更高版本
- 当前受支持版本的 `uv`

## 安装与运行

从仓库根目录执行：

```shell
cd projects/engineering-foundations
uv sync
uv run engineering-demo RAG --log-level INFO
```

命令会把面向用户的搜索结果写到标准输出，把运行事件写到标准错误。使用 JSON 日志或观察 `DEBUG` 阈值：

```shell
uv run engineering-demo RAG --json-logs
uv run engineering-demo RAG --log-level DEBUG
```

程序只记录查询长度，不记录原始查询或文档正文。示例中的 `request_id` 每次运行都会变化，日志时间和耗时也不会固定。

## 运行测试

```shell
uv run pytest
```

现有测试覆盖：

- 搜索词大小写和首尾空格的参数化测试。
- 结果上限和无效上限。
- 空查询的异常、`WARNING` 级别和上下文字段。
- 成功路径的事件顺序和请求 ID 关联。
- JSON formatter 对结构化字段的保留。

只运行一个测试：

```shell
uv run pytest tests/test_search.py::test_empty_query_is_rejected_with_context
```

## 交互式日志实验

`logging-lab/index.html` 是一个无第三方依赖的单页实验。直接在浏览器打开即可：

1. 切换最低日志级别，观察保留和过滤数量。
2. 按事件名或 `request_id` 筛选记录。
3. 点击模拟按钮，比较正常搜索、空查询和索引故障产生的事件。

实验数据只存在当前浏览器页面内，不会上传或写入仓库。

## 代码质量

```shell
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## 目录结构

```text
engineering-foundations/
├── logging-lab/
│   └── index.html              # 日志级别与字段筛选交互实验
├── src/engineering_foundations/
│   ├── cli.py                  # 应用入口，在边界配置日志
│   ├── logging_config.py       # 文本与 JSON formatter
│   └── search.py               # 带结构化事件的搜索逻辑
├── tests/
│   ├── test_logging_config.py
│   └── test_search.py
├── pyproject.toml
└── uv.lock
```

运行项目只使用 Python 标准库；pytest 和 Ruff 是开发依赖，不会成为应用的运行时依赖。
