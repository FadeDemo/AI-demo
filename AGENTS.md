# Repository Agent Instructions

## Scope and precedence

- This file applies to the entire repository.
- A nested `AGENTS.md` may add stricter rules for its own directory. If a nested rule conflicts with this file, follow the more specific nested rule.
- Follow the repository's general Markdown conventions in [`docs/markdown-style-guide.md`](docs/markdown-style-guide.md) in addition to the agent-specific safeguards below.

## Documentation changes

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

### 课程任务的范围与前置能力

- 编写、修改或验收课程任务时，只能把当前课程明确讲解的概念、当前任务明确要求实现的行为，以及先修课程已经引入的契约作为必需范围。不得把代码审查中发现的架构改进、生产环境最佳实践或后续课程能力追加为当前任务的验收要求。
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

### Provider-specific terminology

When documentation names a provider-, product-, API-, model-, or version-specific parameter, endpoint, or behavior, identify its owner and applicable interface at first use. State the generic concept separately from the provider-specific example; do not present a specific identifier as though every provider, API, or model uses it.

When the explanation depends on exact provider-specific behavior, verify it against documentation maintained by that provider and link the source near the explanation when appropriate.

Do not write:

```markdown
`max_output_tokens` controls the output limit.
```

Write:

```markdown
Different providers and APIs use different output-limit parameters. For example, the OpenAI Responses API uses `max_output_tokens`.
```

Before finishing a Markdown change, list code-formatted identifiers in the changed prose and manually verify that the first use of each provider-specific identifier names its owner, interface, and scope:

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
