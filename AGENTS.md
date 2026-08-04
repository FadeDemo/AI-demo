# Repository Agent Instructions

## Scope and precedence

- This file applies to the entire repository.
- A nested `AGENTS.md` may add stricter rules for its own directory. If a nested rule conflicts with this file, follow the more specific nested rule.
- Follow the repository's general Markdown conventions in [`docs/markdown-style-guide.md`](docs/markdown-style-guide.md) in addition to the agent-specific safeguards below.

## Documentation changes

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

## Extending these instructions

- Add future repository-wide rules under a section named for the affected artifact or workflow, such as `Documentation changes`, `Python changes`, `Testing`, or `Version control`.
- Put module-specific rules in a nested `AGENTS.md` near that module instead of adding unrelated detail here.
- Keep each rule testable: state the required behavior, include a failing and passing example when syntax is subtle, and name the verification command when one exists.
- Do not duplicate long tool instructions in this file. Link to the repository's maintained guide and record only the agent-specific requirement or safeguard here.
