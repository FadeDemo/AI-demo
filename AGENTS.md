# Repository Agent Instructions

## Scope and precedence

- This file applies to the entire repository.
- A nested `AGENTS.md` may add stricter rules for its own directory. If a nested rule conflicts with this file, follow the more specific nested rule.
- Follow the repository's general Markdown conventions in [`docs/markdown-style-guide.md`](docs/markdown-style-guide.md) in addition to the agent-specific safeguards below.

## 渐进式学习辅导

- 当用户正在亲自实现代码，并询问下一步要做什么或某一步如何实现时，默认只提供当前最小步骤、目标和验收点，不提前给出完整实现、全量代码或后续所有步骤；只有用户明确要求完整方案或完整代码时才展开。不得因此省略完成当前步骤所必需的约束、安全问题或已经确认的缺陷。

## Documentation changes

### 文档语言

- 本仓库新增或修改的说明性文档默认使用简体中文，包括课程、项目说明、
  设计记录和 Agent 规则文件。
- 代码标识符、命令、API 字段、文件名、路径、产品名称以及需要保持准确的
  外部原文可以保留其原始语言；不要为了满足中文要求而翻译或改写这些内容。

### 课程内容的范围与受众

- 将课程文档视为面向不同学习者的可复用材料。课程说明、任务和验收标准必须在不了解当前仓库具体实现的情况下仍可理解。
- 用户询问现有类、函数、字段、文件或配置的实现问题，并不自动表示允许把相关细节写入课程文档。除非用户明确要求修改课程，否则应在对话或项目文档中回答。
- 课程正文应优先描述概念、职责和行为契约。只有当课程已经明确引入某个仓库标识符，并且完成练习或理解验收标准确实需要它时，才可使用该标识符。
- 修改课程文档前，应区分“用户要求写入课程的内容”和“仅针对当前实现的答疑”，不得把后者擅自持久化到课程中。
- 完成修改前，检查新增内容中对当前项目和具体实现的引用；能够用实现无关的概念表达时，应删除类名、字段名和文件名。

以下内容仅为规则示例，示例中的类名不是唯一受限制的标识符。

不要这样写（反例）：

```markdown
当前项目的 `ModelProfile` 应嵌套 `ModelLimits`。
```

应当这样写（正例）：

```markdown
将模型固有限制保存在应用维护的模型能力配置中；具体采用平铺字段还是嵌套值对象，不属于本任务的验收要求。
```

修改课程文档后，使用以下命令筛选可能依赖当前实现的新增内容，并逐项人工确认：

```shell
git diff --unified=0 -- <changed-course-files> |
  rg '^\+.*(`[^`]+`|当前项目|本项目|现有实现)'
```

命令产生匹配不代表内容一定错误，但每个匹配项都必须确认其是否已由课程引入、是否属于任务所需，以及是否可以改成实现无关的表达。

### 课程文档的当前态自足性

- 课程文档必须以当前文件内容为准保持自足，不得依赖 Git diff、对话记录、审查意见或已经删除、替换的文本才能理解。
- 当任务要求学习者分析、改写或比较某段内容时，必须在当前课程中完整提供该内容，或者链接到仍然存在且可明确定位的版本。
- 不得使用“原始要求”“原描述”“原句”“之前的内容”等表述指代当前文档中不存在或无法唯一定位的内容。
- 只有当版本变化本身属于课程内容，并且相关版本均被保留和明确标记时，才可使用“旧版”“新版”等历史性表述。
- 课程正文应描述最终需要学习或完成的内容，不得把“根据反馈修改”“本次新增”等编辑过程当成课程说明。

以下两个示例描述同一个“改写模糊 Prompt”任务，区别在于学习者能否只根据当前文档找到待改写的内容。

不要这样写（反例）：

```markdown
### 任务：重写模糊 Prompt

原始要求没有说明受众、资料范围和长度。请先找出缺失项，再把它改写成可测试的任务契约。
```

反例只提到“原始要求”，却没有在当前文档中提供或定位这项要求。学习者必须查看 diff、对话或其他编辑记录，才能知道要分析和改写什么。

应当这样写（正例）：

```markdown
### 任务：重写模糊 Prompt

待改写的 Prompt 是：

> 总结下面内容，要准确、专业。

这条 Prompt 没有说明受众、资料范围和长度。请先找出缺失项，再把它改写成可测试的任务契约。
```

正例在当前文档中保留了待改写内容，并用“这条 Prompt”明确引用它；学习者不需要知道课程经历过哪些修改。

修改课程文档后，使用以下命令筛选可能依赖已删除内容或编辑过程的新增表述，并逐项人工确认：

```shell
git diff --unified=0 -- <changed-course-files> |
  rg '^\+.*(原始要求|原描述|原句|之前的内容|此前版本|旧版|新版|根据反馈|本次修改)'
```

该命令只能辅助筛选，既可能误报，也可能漏报。产生匹配不代表内容一定错误，但每个匹配项都必须确认引用对象在当前文档中清晰可见；没有产生匹配也不代表内容一定自足。无论扫描结果如何，完成修改前都必须人工确认新增或编辑的课程内容不依赖 diff、对话、审查意见或已经删除、替换的文本。“旧版”“新版”用于明确的版本比较时可以保留。

### 课程任务的范围与前置能力

- 编写、修改或验收课程任务时，只能把当前课程明确讲解的概念、当前任务明确要求实现的行为，以及先修课程已经引入的契约作为必需范围。不得把代码审查中发现的架构改进、生产环境最佳实践或后续课程能力追加为当前任务的验收要求。
- 采用教学简化策略时，应说明它是本课的选择、选择原因和适用范围，不得将其写成通用的必需条件。
- 每项任务要求和通过条件都必须能够追溯到课程正文已经介绍的概念或行为契约，并对应一个由任务明确要求产生的可观察结果。仅仅存在相关代码、潜在风险或未来使用场景，不构成当前任务的实现要求。
- 如果某项要求依赖尚未引入的数据格式、接口、状态策略、应用模块或后续处理流程，必须选择以下一种处理方式：
  - 在当前课程中先解释该前置能力，并明确要求实现最小的生产者、消费者和可测试边界；
  - 将该要求推迟到正式介绍相关能力的后续课程；
  - 从当前任务和通过条件中删除该要求。
- 验收学习者实现时，必须把“任务范围内的未完成项”和“范围外的可选设计建议”分开报告。范围外观察不得表述为缺陷、关键缺口、阻塞项或未通过原因。
- 不得根据当前实现反向推导课程未声明的行为策略，并据此判定实现错误。

以下示例用于说明如何判断任务是否越过已经引入的课程边界。

示例上下文：

- 先修课程已经定义模型响应包含文本和结束原因。
- 当前课程讲解输出上限，以及如何根据结束原因识别输出截断。
- 当前项目只消费普通文本，没有要求模型返回特定 Schema，也没有结构化数据的解析器或业务消费者。
- 后续课程才会介绍 Schema、结构化输出验证和业务消费边界。

不要这样写（反例）：

```markdown
### 任务：识别截断

用 fake 客户端分别返回结束原因为正常完成和达到输出上限的响应。

通过条件：被截断的结构化输出不得进入后续业务模块。
```

这个要求属于反例，因为当前课程和先修课程都没有定义结构化输出契约、解析器或后续业务模块。学习者若要满足通过条件，就必须自行设计课程未讲解、任务未声明且原项目不存在的能力。

应当这样写（正例）：

```markdown
### 任务：识别截断

用 fake 客户端分别返回结束原因为正常完成和达到输出上限的响应。应用应正常显示前者的文本，并在后者明确提示回答不完整。

通过条件：两个结束原因分支都有测试；判断依据是响应携带的结束原因，不依赖文本是否为空或结尾是否有句号。
```

这个要求属于正例，因为它只使用先修课程已经定义的结束原因，并验证当前课程正在讲解的截断识别行为。显示结果和自动化测试都是任务明确要求且可以直接观察的产物。

再例如，验收时发现应用会把截断文本保存到对话历史，但课程没有定义失败响应的历史保存策略。此时可以把它报告为需要以后决定的设计问题，但不得把它列为当前任务的未完成项。只有课程先定义了相应策略并把它写入任务或通过条件，才能据此验收。

### 实现任务的能力增量与编排检查

- 实现类课程的每个独立任务必须明确新增的应用行为、协议、执行边界或可运行流程，以及学习者完成后可以观察到的结果。仅补充已有行为的测试、格式化或 lint，默认归入对应实现任务的验收与收尾，不单独编号为实现任务。专门讲解测试方法的章节可以安排独立测试任务，但须明确其测试设计学习目标；知识检查和书面分析任务不受实现任务的产物要求限制。
- 编写或调整任务时，逐项核对“新增能力 → 前置能力及其所属任务 → 应用中的触发入口 → 可观察结果 → 验收证据”。前置能力必须由先修内容、更早的任务或当前任务先实现的明确步骤提供；不得用笼统的任务标题推定已经具备连续处理、历史保存等能力。
- 引导学习者开始新任务前，重新核对课程正文、已确认的验收边界及相关实现，用简短说明交代本任务新增什么、复用什么、通过哪个入口验证。逐步辅导可以拆分实现步骤，但不能因此跳过整项任务的依赖检查。
- 验收须区分组件测试和应用流程测试。组件测试可以直接调用内部函数验证组件契约；要求通过应用入口完成的场景，必须由该入口驱动。不得在测试中手动补做应用尚不支持的步骤，却把结果报告为应用流程已经实现。测试替身可以控制外部响应，但不能替应用补齐被验收的流程。
- 验证拒绝或保护机制时，输入必须实际到达该机制，并检查拒绝类别或停止原因及执行记录。仅因为后续调用未接入、流程提前结束或请求根本未被处理而没有执行目标操作，不能证明授权、注册表校验或循环保护有效。
- 发现能力已由此前任务提供，或验收依赖后续任务时，应先合并重复任务、调整顺序或明确较小的验收范围，再继续布置练习。不得为了保留任务编号而临时增加无依据的实现要求，或反复改写测试来绕过依赖问题。保留已有的有效实现与回归测试，不以编排修订追溯推翻按已确认范围通过的验收。

例如，前一任务只要求一次工具回传时，“工具结果回传后，模型再次提出未注册调用，应用返回拒绝结果”的应用流程验收依赖连续工具处理。应将该场景放入明确实现连续处理的任务，并由应用入口驱动；直接在测试中再调用一次执行器，只能证明执行器的拒绝契约，不能证明应用已经接通连续处理。

### Markdown emphasis boundaries

When bold text is followed by continuing prose, place one ASCII space after the closing `**`. This is required even when Prettier and markdownlint report no problem, because some Markdown renderers do not recognize a closing emphasis delimiter that touches the following letter or CJK character.

Do not place the bold segment `**标准输出（stdout）**` immediately before the prose `用于程序正常产生的结果。` without a space. Likewise, do not place the bold list-item title `**对照文本日志和 JSON 日志。**` immediately before `在仓库根目录执行。`

Write:

```markdown
**标准输出（stdout）** 用于程序正常产生的结果。

1. **对照文本日志和 JSON 日志。** 在仓库根目录执行。
```

Punctuation may directly follow bold text when normal typography requires it, for example `**important**：`. The mandatory space applies when the next character is a letter or number, including CJK characters.

### Markdown validation

For every Markdown change:

1. Format the changed Markdown files with the repository-local Prettier.
2. Scan the changed files for a bold closing delimiter followed immediately by a letter or number. The following command must produce no matches:

   ```shell
   rg -nP '`[^`\n]*`(*SKIP)(*F)|\*\*[^*\n]+\*\*(?![\p{L}\p{N}])(*SKIP)(*F)|\*\*[^*\n]+\*\*(?=[\p{L}\p{N}])' <changed-markdown-files>
   ```

3. Lint the changed Markdown files with the repository-local `markdownlint-cli2`.
4. Inspect newly added or edited emphasis manually when rendered output is part of the reported issue. Formatter and linter success alone is not sufficient verification for delimiter-boundary defects.

### 图示中的连接线与箭头

- 修改 SVG 或其他图示中的连接线时，线段必须从源节点的外边界发出，并在目标节点的外边界结束；不得把端点放在节点内部或与边界之间留下无意的空隙。
- 连接矩形节点的左、右边缘时，如果语义和布局没有要求偏移，默认使用对应边缘的垂直中点；连接上、下边缘时默认使用水平中点。连接线可以使用直线或曲线，但箭头尖端必须准确落在预期位置，且接入方向清晰，不得产生视觉偏移。
- 连接线路径不得穿过无关节点、节点文字或其他箭头。需要绕行时，应保留足够间距，并让起点、终点和流向仍能一眼辨认。
- 完成图示修改后，必须按完整画布和原始宽高比渲染并人工检查所有连接线。检查每条线的起点、终点、箭头方向、接入位置以及与其他元素的交叉情况；只通过 XML 解析、格式化或查看被裁切的缩略图不能代替这项检查。

### 课程表达的完整性与简洁性

- 精简句子时，应保留理解所必需的主体、动作、条件和结果。上下文已明确的信息可以省略，但不得产生歧义或要求学习者猜测处理流程。
- 不得为了省字，将完整条件压缩成含义不清的短语。例如，“读取异常”可能表示读取过程中发生异常，也可能表示读取一个异常对象，应根据实际含义展开。
- 使用“则”“因此”“否则”等连接词时，应确保对应的条件、因果依据或分支关系清楚可见；连接词本身不能替代这些说明。条件表达明确时可以使用“则”，不应将这条规则理解为禁止某个连接词。
- 完成课程文档修改前，人工检查新增或编辑的行为说明：读者能否明确判断“什么情况下，由谁执行什么动作，产生什么结果”。不必每句重复全部信息，但理解当前说明所必需的信息必须能从当前上下文确定；格式化和 lint 不能替代这项检查。

以下示例假设课程已说明“消费者”是负责读取和处理响应事件的应用代码。

不要这样写（反例）：

```markdown
读取异常则记录相应失败类别。
```

应当这样写（正例）：

```markdown
读取过程中发生异常时，消费者应记录对应的失败类别。
```

正例明确保留了异常发生的条件、执行主体和处理动作，避免读者把“读取异常”误解为读取某个异常对象。

### 术语引入、分类与适用范围

#### 课程术语与分类

- 首次引入影响课程理解、任务实现或验收的术语时，应先说明它指什么，以及它与已经讲解的概念有什么关系，再在正文、任务或通过条件中使用。先修课程已定义的概念可以明确引用其所在课程或章节，不必重复展开。
- 使用“普通”“特殊”“模式”“类型”等分类性称呼前，应说明分类依据及本课涉及的类别。只介绍理解当前内容所需的范围，不为解释一个名称额外引入课外体系；不能让读者自行推测类别按输出用途、数据格式还是处理方式划分。
- 区分通用概念、提供方或 SDK 的术语，以及课程自行采用的称呼。课程自定义的名称必须说明含义和适用范围，不能让读者误以为它是行业、模型接口或 SDK 规定的分类。
- 同一概念应保持称呼一致；确需采用别称或换一种表达时，应先说明两者的关系。不同概念也不能仅因相关就交替使用同一个名称，不能让读者自行猜测是否出现了新概念。

以下示例假设先修课程已讲解提供方适配层、结构化验证和工具执行，当前课程只要求增加回答正文的流式展示。

不要这样写（反例）：

```markdown
普通文本流式模式需要三类事件。
```

这个表述没有解释“普通文本”的分类依据，也没有说明“模式”属于模型接口、SDK 还是应用自己的处理流程。

应当这样写（正例）：

```markdown
本课按输出用途划定练习范围：供用户阅读的回答正文用于展示，结构化数据需要交给程序验证，工具参数需要交给执行器校验。本课只为回答正文实现流式展示；结构化数据和工具参数继续使用已有的完整响应处理流程。

适配层将 SDK 事件转换成应用自己的事件。用于逐段展示回答正文的应用事件协议，至少需要表达文本增量、用量统计和终止事件。
```

这个示例直接说明输出用途、练习范围和协议归属，不需要学习者自行推测“普通模式”意味着什么；“已有处理流程”指示例上下文已声明由先修课程提供的能力。

#### 提供方专属术语

- 文档提及提供方、产品、API、模型或版本专属的参数、端点或行为时，必须在首次使用处标明所属提供方或产品、适用接口和范围。先说明通用概念，再给出提供方专属示例；不得把某个具体标识符写成所有提供方、接口或模型都采用的通用名称。
- 用某个提供方或接口说明通用概念时，应以“例如”等明确措辞引入，避免暗示课程要求采用该提供方或接口。
- 解释依赖提供方的精确行为时，必须依据该提供方维护的文档核实，并在适当情况下将来源链接放在相关说明附近。

不要这样写（反例）：

```markdown
`max_output_tokens` 控制输出上限。
```

应当这样写（正例）：

```markdown
不同提供方和 API 使用不同的输出上限参数。例如，OpenAI Responses API 使用 `max_output_tokens`。
```

#### 验证要求

- 完成课程文档修改前，逐项检查新增或编辑的术语与分类名称：定义是否先于使用或能明确定位到先修内容，分类依据与本课涉及的类别是否清楚，与前文的关系及所属范围是否明确，后文称呼是否一致。检查对象包括未使用行内代码格式的名称；格式化、lint 和标识符扫描不能替代这项人工检查。
- 完成 Markdown 修改前，使用以下命令列出行内代码格式的标识符，并逐项人工确认提供方专属标识符的首次使用已说明所属提供方或产品、接口及适用范围：

  ```shell
  rg -n '`[A-Za-z][A-Za-z0-9_.-]*`' <changed-markdown-files>
  ```

### Learning status metadata

The YAML front matter `status` field describes the learner's progress, not whether an agent has finished authoring the document.

- Use `planned` for a newly created course, concept note, or experiment unless the user explicitly states that learning has already started or finished.
- Use `learning` when the user explicitly states that the learner has started or is continuing the material. Active participation also counts as explicit progress evidence: use `learning` when the user works through required material by answering course questions, implementing or debugging exercises, or requesting an acceptance check for a course task.
- Do not infer `learning` merely because the user asks an agent to create, rewrite, or polish course content for future use without participating in the material or exercises.
- Use `completed` only when the user explicitly confirms that the learner has completed the material. Do not infer completion from a polished document, complete lesson content, passing repository checks, existing exercises, or generated answer templates.
- A course index must not be marked `completed` merely because all child course documents have been written.
- Use the `updated` field, not `status`, to record that document content was created or revised.
- 当对话涉及整课验收，或 Agent 给出整课验收结论时，必须核对对应课程文件及已存在的回答记录的学习状态，即使这些文件尚未修改或暂存；状态是否需要更新仍按本节原有的学习进度规则判断，需要修改的关联文件须纳入本次收尾和提交范围。

Do not write this for a newly generated course whose learner progress is unknown:

```yaml
status: completed
```

Write:

```yaml
status: planned
```

Before finishing any change that creates or edits learning-note front matter, run the following command and verify every listed value against explicit user-provided progress information:

```shell
rg -n '^status:' <changed-learning-note-files>
```

Before each commit that creates or modifies a course, concept note, experiment, or answer record, review the YAML front matter even when the staged diff does not directly edit it. For every staged learning-note file:

- Update `updated` to the current date when the document content was materially revised.
- Verify `status` against explicit learner-progress evidence from the current conversation.
- Do not change `status` merely because implementation, tests, authoring, formatting, or other repository work is complete.
- Use `completed` only after the user explicitly confirms completion of the learning material.

Run the following command before committing and verify every listed value:

```shell
rg -n '^(status|updated):' <staged-learning-note-files>
```

### Course tasks and answer records

Course documents must remain complete and usable before a learner creates any personal answer document. State each written prompt and its acceptance criteria directly in the course document; do not link task instructions to `answers/` files or assume those files already exist.

Files under an `answers/` directory are personal records created while completing exercises, not prerequisites or worksheets distributed by the course. An answer file may link back to its course, and an answer index may list the file after it exists, but the course must not depend on the answer file.

Do not write:

```markdown
在[练习回答](answers/example.md)的对应小节中说明三种替身的区别。
```

Write:

```markdown
以书面形式说明 Stub、Fake 和 Mock 分别控制或验证了什么。
```

Before finishing a course-document change, manually verify that every newly added or edited task can be understood and completed without opening a personal answer file. Formatter and linter success do not replace this semantic check.

## Execution hygiene

### Spawned process lifecycle

Treat every command that may outlive its immediate caller as a managed process. This includes browsers, GUI applications, preview or conversion tools, development servers, watchers, background jobs, and commands that can leave worker or helper processes behind.

Before launching a managed process:

- Prefer a tool that exits deterministically when it can perform the same task.
- Give the invocation a task-unique signature, such as a dedicated temporary path, and record every returned PID, process-tree root, session ID, or tool-specific handle.
- Define a bounded wait condition and a cleanup procedure before starting the process. Do not rely on a successful tool return, timeout, error, or interrupted session to prove that child processes exited.

On every terminal path, including success, failure, cancellation, timeout, and fallback:

- Inspect the recorded process or session and any task-identified descendants.
- Request graceful termination first, wait for exit, and use forced termination only for the exact agent-owned processes that remain.
- Verify that the recorded PIDs, sessions, and task-unique signature no longer identify a live process before reporting completion or removing its temporary directory.

Never terminate processes by a broad application or executable name when the user may be running the same application. Resolve exact agent-owned targets from recorded identifiers and command lines; leave unrelated user processes untouched.

Do not launch an unbounded process and assume the calling tool will clean it up:

```shell
firefox --headless --screenshot preview.png page.html
```

A compliant workflow must capture the launched process or session identifier, wait only within an explicit bound, clean up the exact recorded target, and then verify both the identifier and task signature. For example:

```shell
ps -p <recorded-pid> -o pid=,ppid=,etime=,%cpu=,command=
ps -axo pid=,ppid=,etime=,%cpu=,command= | rg '<task-unique-signature>'
```

After cleanup, both verification commands must produce no process matches other than the verification command itself. If verification is unavailable or inconclusive, do not claim cleanup succeeded; report the unresolved process identifiers and continue with the safest exact-target check available.

## Version control

### Default scope for commit requests

When the user explicitly asks to commit, submit, or push without naming a narrower scope, treat every current non-temporary repository change as part of the requested scope, including changes that existed before the current turn. Do not silently omit a changed or untracked file merely because it appears unrelated, predates the current task, or was authored by the user.

Before staging, record the complete initial change set with:

```shell
git status --short --untracked-files=all
```

An initial change may remain outside the commit only when it is:

- explicitly excluded by the user;
- an agent-created temporary file that must be cleaned instead of committed;
- generated or ignored output that repository rules say not to commit; or
- blocked by a concrete safeguard, such as detected sensitive information, failed required formatting or linting, or an unresolved scope conflict.

If a safeguard blocks any initial change, stop before pushing, list the exact excluded path and reason without exposing sensitive content, and request user direction. Do not choose a narrower commit scope on the user's behalf. Changes may be split into multiple coherent commits, but every initial change must be included, explicitly excluded, cleaned under the temporary-file rules, or reported as blocked.

After the final commit and before pushing, run the status command again and reconcile it with the initial change set. If any non-ignored initial change remains without an allowed exclusion, the commit request is incomplete and must not be reported as complete.

Do not do this:

```text
User: Commit and push.
Agent: Commits only files changed during the latest task and silently leaves older modifications unstaged.
```

Do this:

```text
User: Commit and push.
Agent: Commits every current eligible change, or stops before pushing and identifies each blocked path and reason.
```

## Extending these instructions

- Add future repository-wide rules under a section named for the affected artifact or workflow, such as `Documentation changes`, `Python changes`, `Testing`, or `Version control`.
- Put module-specific rules in a nested `AGENTS.md` near that module instead of adding unrelated detail here.
- Keep each rule testable: state the required behavior, include a failing and passing example when syntax is subtle, and name the verification command when one exists.
- Do not duplicate long tool instructions in this file. Link to the repository's maintained guide and record only the agent-specific requirement or safeguard here.
