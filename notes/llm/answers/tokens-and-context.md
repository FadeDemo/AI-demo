---
title: Token 与上下文窗口练习回答
type: answer
area: llm
status: learning
created: 2026-08-12
updated: 2026-08-12
tags:
  - llm
  - token
  - answers
---

# Token 与上下文窗口练习回答

本文保存 [Token 与上下文窗口](../tokens-and-context.md)课程中需要书面留档的计数结果、观察结论和知识检查。当前先记录任务 1；可重复执行的样本、计数入口和命令统一维护在 [LLM Terminal Assistant 项目](../../../projects/llm-terminal-assistant/README.md)中，后续任务的实现和验证方式也保存在该项目中。

## 任务 1：比较目标模型的 Token 计数

### 目标模型与计数实现

终端项目选用的目标模型标识是 `deepseek-v4-flash`。为了使用与该模型匹配且可复现的分词规则，计数入口从 DeepSeek 在 Hugging Face Hub 发布的 [`deepseek-ai/DeepSeek-V4-Flash-0731`](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) 模型仓库加载配套 tokenizer，并固定到 revision `7872f01b1d1fe23eabc4c98b48bffcef5a386062`。DeepSeek 在该仓库的模型卡中示范了通过 Hugging Face Transformers 的 `AutoTokenizer.from_pretrained()` 加载配套 tokenizer，计数入口沿用这一接口。

计数入口使用 Hugging Face Transformers 4.57.6 的 `AutoTokenizer` 加载 tokenizer；本次实际环境中的底层 Hugging Face Tokenizers 版本是 0.22.2，加载后的 tokenizer 类型是 `PreTrainedTokenizerFast`。项目调用 Hugging Face Transformers tokenizer 的 `encode(text, add_special_tokens=False)`，再计算返回的 Token ID 数量。`add_special_tokens=False` 表示不自动加入 BOS、EOS 等模型特殊 Token，因此这里统计的是每个样本原始文本本身，不是带角色和消息边界的完整聊天请求。

### 样本与计算方法

四份样本均位于项目的 `samples/token-counting/` 目录：

- 中文：`samples/token-counting/chinese.txt`
- 英文：`samples/token-counting/english.txt`
- JSON：`samples/token-counting/data.json`
- Python 代码：`samples/token-counting/example.py`

计数入口使用 Python `Path.read_text(encoding="utf-8")` 读取文件原始文本，并使用 Python `len(text)` 计算解码后字符串的字符数。字符数包含空格、标点、缩进、换行和文件末尾换行。JSON 与 Python 文件不经过重新序列化或 AST 转换，避免改变 tokenizer 实际接收的文本。

实际安装与执行命令、首次缓存的网络行为以及严格离线复现方式统一记录在项目 README 的 [Token 计数](../../../projects/llm-terminal-assistant/README.md#token-计数)小节。本次结果使用该小节中的严格离线命令复现，运行时没有访问 Hugging Face Hub。

### 计数结果

以下结果来自相同模型仓库、revision 和计数工具版本下的一次离线复现：

| 样本类型    | 项目内路径                           | 字符数 | Token 数 |
| ----------- | ------------------------------------ | -----: | -------: |
| 中文        | `samples/token-counting/chinese.txt` |     50 |       32 |
| 英文        | `samples/token-counting/english.txt` |    119 |       25 |
| JSON        | `samples/token-counting/data.json`   |    154 |       60 |
| Python 代码 | `samples/token-counting/example.py`  |    271 |       77 |

### 观察结论

四类样本的字符数与 Token 数关系明显不同：50 个中文样本字符得到 32 个 Token，而 119 个英文样本字符得到 25 个 Token；JSON 和 Python 代码又呈现不同关系。tokenizer 的词表不是本次切分产生的结果，而是 tokenizer 训练后固定并随模型发布的 Token 片段与 Token ID 映射。运行时，tokenizer 按既定的文本规范化、预切分和子词算法，从这些 Token 片段中确定当前文本的切分结果。Hugging Face Tokenizers 的[分词流水线说明](https://huggingface.co/docs/tokenizers/main/pipeline)区分了这些阶段。因此，文本内容、词表和算法规则都会影响 Token 数，不同文本不会遵循固定的“每字符对应多少 Token”比例。

本任务只比较原始样本文本。真实聊天请求还可能包含角色、消息边界、工具定义和生成提示等编码开销，不能把各条消息正文的 Token 数简单相加后当作完整请求计数。请求完成后的实际记账应以模型服务返回的 usage 为准。
