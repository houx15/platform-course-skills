# 平台课程标准化 Skills 设计

日期：2026-08-06

## 1. 背景

教师已经拥有 Word、HTML、Markdown、PDF、PPT 等不同格式的课程材料，但这些材料通常不能完整表达平台所需的课程结构、互动方式、阻塞条件、答案、反馈、视频暂停点和 HTML 数据提交协议。

本项目提供一组供 Claude Code 和 Codex 使用的 Skills。教师只调用一个入口并提交现有材料，AI 负责分析材料、发现信息缺口、提出课程结构、完成专项互动设计、生成标准课程并执行上传前验收。

当前目录中的 `index.md` 是课程入口样例。ZIP 是无关导出物，不作为输入规范，也不参与验收。

## 2. 目标

1. 将教师已有材料转化为结构稳定、可机械验证的平台课程。
2. 保留原始材料中的有效内容，并记录每个内容点的处理去向。
3. 对原始材料没有表达的必要信息主动向教师提问。
4. 无论材料是否提到，都明确确认是否需要长视频和独立 HTML 交互。
5. 在完整课程编排前优先完成复杂媒体的详细设计。
6. 使用结构化 JSON 作为课程和视频交互的唯一事实源。
7. 自动生成供教师和平台人工查看的 Markdown。
8. 使用独立 Review 和确定性脚本共同判断课程是否可上传。
9. 同一份 Skill 源码同时支持 Claude Code 和 Codex。

## 3. 非目标

1. 不生成、剪辑或修改 MP4。
2. 不把 ZIP 作为平台交付要求。
3. 不仅凭 AI 的主观判断宣称课程符合机械格式。
4. 不证明真实学生一定获得学习效果。
5. 首版不支持样例之外的任意自定义内容块类型。

## 4. 已发现的样例问题

当前样例只能用于理解方向，不能原样作为严格验收标准：

1. `video_example.mp4` 时长约 32.5 秒，但交互文档包含 `01:30` 时间点。
2. HTML 指南要求入口文件名为 `index.html`，课程入口实际引用 `example.html`。
3. HTML 指南将 `4:3` 称为竖向矩形，但推荐尺寸 `1024 × 768` 和示例均为横向。
4. `index.md` 中 HTML 指南链接缺少 `.md` 扩展名。
5. 样例中的括号说明属于模板注释，不应进入最终课程。

正式规范以本文、JSON Schema 和校验脚本为准，不从这些冲突细节推断规则。

## 5. 用户体验

教师只需要提出类似请求：

> 请把这些材料整理成可上传的平台课程。

AI 对教师呈现的内容只有：

1. 对原始材料的理解摘要。
2. 发现的矛盾、重复和关键信息缺口。
3. 是否使用长视频或 HTML 交互的明确问题。
4. 视频交互或 HTML 交互的可读设计稿。
5. AI 提议的 Part/Piece 课程结构。
6. 无法可靠推断且影响课程结果的必要问题。
7. 每个 Part 的简洁预览。
8. 最终课程目录和 Review 结论。

教师不需要理解 Skill 的拆分、JSON Schema 或校验脚本。

## 6. 总体架构

采用“一个入口、多个内部专家、双层验收”：

```text
教师提交原始材料
        ↓
材料审计与原文覆盖表
        ↓
长视频 / HTML 交互识别与明确追问
        ↓
复杂媒体专项设计
        ↓
课程 Part/Piece 方案确认
        ↓
逐部分补齐必要信息
        ↓
生成结构化课程与可读视图
        ↓
独立内容 Review + 确定性格式校验
        ↓
自动修复或返回教师确认
        ↓
可上传结论
```

## 7. Skill 分工

### 7.1 `build-platform-course`

唯一教师入口，负责：

- 接收材料路径和教师目标。
- 调度其他 Skills。
- 保存和恢复构建进度。
- 控制确认节点。
- 防止重复提问。
- 生成最终课程。
- 完成后强制调用 Review。

### 7.2 `analyze-course-materials`

负责：

- 提取 DOCX、HTML、Markdown、纯文本等材料。
- 使用环境已有能力读取 PDF、PPT 等文件。
- 建立原始内容覆盖表。
- 发现重复、矛盾、缺失和不支持的文件。
- 识别视频与 HTML 交互候选。
- 不得静默跳过无法读取的输入。

### 7.3 `design-course-html`

负责：

- 明确互动的学习目标。
- 设计学生看到的内容、操作、状态和反馈。
- 定义完成条件和提交数据。
- 先请教师确认可读设计，再生成 HTML。
- 检查 iframe 画布、溢出、完成按钮和消息协议。

### 7.4 `design-video-interactions`

负责：

- 设计结构化 MP4 交互，不处理视频本身。
- 有 MP4 时读取实际时长。
- 没有最终 MP4 时使用语义锚点和待对齐状态。
- 补齐暂停点、提示、题型、选项、答案、反馈和阻塞规则。
- 生成视频交互 JSON 和 Markdown。

### 7.5 `review-platform-course`

负责：

- 独立重读原材料、确认记录和最终课程。
- 检查原始内容覆盖和 AI 新增内容的授权。
- 调用确定性校验脚本。
- 检查教学流程的静态完整性。
- 自动修复无语义风险的问题。
- 对实质性问题返回教师确认。
- 输出上传结论。

## 8. 教师对话流程

### 8.1 接收与理解材料

AI 不修改原始文件。它提取课程名称、教学目标、知识内容、案例、活动、问题、媒体资源和已有答案，并给每个有效信息点建立稳定编号及来源位置。

AI 首先展示简洁的材料理解摘要，请教师纠正整体理解。此时不要求教师一次性补全全部细节。

### 8.2 复杂媒体判断

AI 扫描以下信号：

- 长视频、观看视频、某分钟暂停、视频提问、MP4。
- 模拟、实验、拖动、匹配、探索、点击操作、网页活动、HTML。

发现候选时，AI 说明判断依据并建议优先设计。没有发现时，仍必须明确询问课程是否计划使用长视频或独立 HTML 交互。不得因材料未提到就默认没有。

### 8.3 视频交互设计

有 MP4 时：

1. 读取视频时长。
2. 提议暂停位置。
3. 补齐每个事件的提示、互动、答案、反馈和阻塞规则。
4. 检查事件时间严格位于视频时长范围内。

没有最终 MP4 时：

1. 使用“内容发生位置”的语义锚点。
2. 将 `timeSeconds` 设为 `null`。
3. 将状态设为 `needs-timing`。
4. 获得最终 MP4 后再对齐准确时间。

存在 `needs-timing` 时不得判为可上传。

### 8.4 HTML 交互设计

AI 先输出可读设计，至少包含：

- 学习目标。
- 学生看到什么。
- 学生执行什么操作。
- 操作状态和反馈。
- 正确答案或评价方法。
- 完成按钮何时可用。
- 提交哪些 interaction 数据。

教师确认设计后，AI 才生成单文件 HTML。

### 8.5 课程结构确认

复杂媒体设计确认后，AI 提出完整课程方案：

| Part/Piece | 教学作用 | 内容形式 | 来源材料 | 是否阻塞 | 待确认 |
|---|---|---|---|---|---|

每个原始信息点必须处于以下状态之一：

- 安排到某个 Piece。
- 合并或改写，并记录去向。
- 建议舍弃，并获得教师明确同意。

教师先确认总体结构，AI 不在确认前生成全部最终文件。

### 8.6 逐 Part 补齐

AI 只询问无法可靠推断且会影响结果的问题，例如：

- 学生完成后应理解或做到什么。
- 当前内容是讲解、练习还是评价。
- 答错后如何反馈。
- 是否必须完成才能继续。
- 开放题的评价要求。

可以可靠推断的内容由 AI 提出建议供教师确认。每完成一个 Part，AI 展示简洁预览后再继续。

### 8.7 生成与 Review

AI 从结构化数据生成最终文件，随后调用 Review。机械问题自动修复并重新检查；改变教学意义的问题必须返回教师确认。

## 9. 工作目录与上传边界

```text
教师原有仓库/
├── 原始材料……
├── .course-work/
│   ├── session.json
│   ├── source-coverage.json
│   ├── decisions.json
│   ├── unresolved.json
│   └── designs/
└── course/
    ├── course.json
    ├── index.md
    ├── assets/
    │   ├── images/
    │   └── videos/
    └── interactions/
        ├── html/
        └── video/
```

`.course-work/` 保存工作状态和可追溯记录，不上传。`course/` 是唯一上传目录。ZIP 可以存在于教师仓库中，但始终被忽略。

## 10. 课程结构化主数据

`course/course.json` 是课程结构的唯一事实源。`course/index.md` 是确定性生成的可读视图，不独立维护。

顶层结构：

```json
{
  "schemaVersion": "1.0",
  "course": {
    "id": "science-denial",
    "title": "科学否认的五种手法",
    "language": "zh-CN",
    "parts": []
  }
}
```

层级语义：

- `course`：一门课程。
- `part`：平台中的一页。
- `piece`：页面内点击一次出现的内容组。
- `block`：Piece 中按顺序呈现的具体内容。

所有 ID 在课程内唯一，格式为小写字母、数字和连字符。

## 11. 首版内容块

首版只允许以下 6 种内容块：

### 11.1 `text`

必填字段：

- `id`
- `type`
- `content`

### 11.2 `images`

必填字段：

- `id`
- `type`
- `items`

每个 item 包含：

- `source`：课程目录内的相对路径。
- `alt`：非空替代文本。

### 11.3 `video`

必填字段：

- `id`
- `type`
- `blocking`
- `source`

有暂停交互时增加：

```json
{
  "interaction": {
    "data": "interactions/video/warming.json",
    "document": "interactions/video/warming.md"
  }
}
```

### 11.4 `interactiveHtml`

必填字段：

- `id`
- `type`
- `blocking`
- `source`

### 11.5 `fillBlank`

必填字段：

- `id`
- `type`
- `blocking`
- `prompt`
- `assessment`

`assessment.mode` 允许：

- `graded`：包含 `acceptedAnswers`，可选择 `caseSensitive` 和反馈。
- `reflection`：包含明确的 `rubric`。

### 11.6 `singleChoice`

必填字段：

- `id`
- `type`
- `blocking`
- `prompt`
- `options`
- `assessment`

每个 option 包含稳定 ID 和非空 label。

`assessment.mode` 允许：

- `graded`：包含 `correctOptionId`，可包含正确和错误反馈。
- `survey`：不得设置正确答案。

## 12. 路径与资源规则

1. 所有课程资源使用相对于 `course/` 的 POSIX 路径。
2. 不允许绝对路径。
3. 不允许通过 `..` 跳出课程目录。
4. 不允许引用不存在的文件。
5. 图片必须有非空 `alt`。
6. HTML 是单文件交付，CSS 和 JavaScript 内嵌。
7. ZIP 不生成、不引用、不检查。

## 13. 视频交互结构化主数据

每个带暂停交互的视频使用独立 JSON 作为事实源，并生成同名 Markdown 视图。

```json
{
  "schemaVersion": "1.0",
  "video": {
    "source": "assets/videos/warming.mp4",
    "durationSeconds": 195,
    "events": [
      {
        "id": "credibility-check",
        "timeSeconds": 8,
        "blocking": true,
        "prompt": "视频中的内容一定可信吗？",
        "interaction": {
          "type": "singleChoice",
          "options": [
            {"id": "yes", "label": "可信"},
            {"id": "no", "label": "不可信"}
          ],
          "assessment": {
            "mode": "survey"
          }
        }
      }
    ]
  }
}
```

最终 MP4 尚未提供时，事件使用：

```json
{
  "anchor": "视频第一次提出三摄氏度升温影响之后",
  "timeSeconds": null,
  "status": "needs-timing"
}
```

视频交互 JSON 中的资源路径与 `course.json` 一样，统一相对于 `course/` 根目录解析。事件的时间必须递增、不得冲突，并严格小于视频实际时长。

## 14. `index.md` 生成规则

`index.md` 只由 `course.json` 生成：

1. 课程标题使用一级标题。
2. Part 使用二级标题。
3. Piece 使用三级标题。
4. Block 按 JSON 数组顺序生成。
5. 内容类型标签使用固定中文形式。
6. 模板说明和括号注释不进入最终文件。
7. 资源使用有效 Markdown 相对链接。
8. 相同 JSON 必须生成字节一致的 Markdown。

如果现有 `index.md` 与重新生成结果不一致，Review 失败。

## 15. HTML 契约

每个 HTML 交互必须：

1. 使用单个 HTML 文件。
2. 可在 iframe 中完整呈现。
3. 采用 `1:1` 或横向 `4:3` 固定画布，并允许整体缩放。
4. 无横向滚动。
5. 重要内容不超出可视区域。
6. 包含明确的“完成”或“完成任务”按钮。
7. 在满足完成条件前阻止错误提交。
8. 点击完成后调用 `window.parent.postMessage`。
9. 提交以下基础结构：

```json
{
  "type": "INTERACTION_COMPLETE",
  "version": "1.0",
  "payload": {
    "lessonId": "lesson-id",
    "duration": 120,
    "interactions": []
  }
}
```

每个 interaction 包含：

- `interactionId`
- `type`
- `answer`

有客观答案时可包含：

- `correctAnswer`
- `isCorrect`

需要记录耗时时可包含：

- `duration`

静态检查可以证明必要代码和字段存在，不能替代真实 iframe 中的浏览器运行验证。

## 16. 原始内容覆盖

`.course-work/source-coverage.json` 为每个原始信息点记录：

- 稳定 ID。
- 来源文件。
- 来源位置。
- 内容摘要。
- 当前状态。
- 课程去向。
- 是否经过教师确认。

允许状态：

- `unresolved`
- `mapped`
- `merged`
- `discard-proposed`
- `discard-approved`

最终 Review 不允许存在 `unresolved` 或未经批准的 `discard-proposed`。

AI 新增的实质性教学内容必须记录到 `decisions.json`，包括内容、理由、教师确认状态和影响范围。

## 17. 状态保存与增量更新

`.course-work/session.json` 保存当前阶段和最近完成的确认节点。

恢复时：

- 不重复询问已确认问题。
- 检测新材料和发生变化的材料。
- 只重新打开受影响的 Part/Piece。
- 保留所有未解决问题。
- 不因文件已经生成而自动将问题标记为解决。

## 18. Review 与修复边界

AI 可以自行修复：

- 格式和缩进。
- 派生 Markdown 漂移。
- 可确定的相对路径错误。
- 明显的 ID 格式错误。
- 不改变教学意义的 HTML 协议问题。

AI 必须询问教师：

- 删除、合并或实质改写原始内容。
- 改变 Part/Piece 划分。
- 新增教学观点、答案或评价标准。
- 改变阻塞规则。
- 选择视频暂停位置。
- 改变 HTML 的核心互动方式。

## 19. 阻塞内容的完成语义

首版内容块使用以下默认完成语义：

- `video`：视频播放结束，并且所有阻塞视频事件已经提交。
- `interactiveHtml`：平台收到该 HTML 发出的有效 `INTERACTION_COMPLETE` 消息。
- `fillBlank`：学生提交非空答案；`graded` 模式是否必须答对由教师确认。
- `singleChoice`：学生提交一个有效选项；`graded` 模式是否必须答对由教师确认。

如果教师需要不同规则，必须在内容块中提供显式 `completion` 配置并经过确认。Review 不得从“阻塞”一词自行推断重试次数、正确率或放行策略。

## 20. 上传判定

输出仅允许以下三种结论：

- `可上传`
- `修改后可上传`
- `缺少必要材料，暂不可上传`

以下任一情况存在时不得判为可上传：

1. JSON Schema 不通过。
2. ID 重复或层级非法。
3. 路径越界或引用文件缺失。
4. `course.json` 与 `index.md` 不一致。
5. 视频交互 JSON 与 Markdown 不一致。
6. 原材料存在未处理内容点。
7. AI 加入未经确认的实质内容。
8. HTML 缺少完成按钮、提交协议或必要数据字段。
9. 视频事件超出实际时长。
10. 视频交互包含 `needs-timing`。
11. 阻塞活动缺少完成条件。
12. 客观题缺少答案。
13. 开放题缺少评价要求。

## 21. 确定性工具

### 21.1 `extract-materials.py`

- 使用标准库直接提取 DOCX、HTML、Markdown 和纯文本。
- 保留来源位置。
- 报告不能读取的文件。

PDF、PPT 等格式由 `analyze-course-materials` 检查当前 AI 环境可用的文档能力后处理；无法可靠读取时要求教师导出为 DOCX、HTML、Markdown 或纯文本。脚本本身不得声称已提取它不支持的格式。

### 21.2 `render-index.py`

- 从 `course.json` 生成 `index.md`。
- 输出确定、可重复。

### 21.3 `render-video-interactions.py`

- 从视频交互 JSON 生成 Markdown。
- 时间统一显示为 `MM:SS` 或 `HH:MM:SS`。

### 21.4 `validate-course.py`

- 检查 Schema。
- 检查 ID、层级、路径和文件。
- 读取 MP4 时长并检查事件。
- 静态检查 HTML。
- 重新生成并比较派生 Markdown。
- 默认忽略 ZIP。

脚本优先只使用 Python 标准库，避免教师安装复杂依赖。

## 22. Skill 分发

Skill 源码只维护一份。工具包提供安装方式，将同一组 Skill 暴露给：

- Codex：`.agents/skills/`
- Claude Code：`.claude/skills/`

使用两端都支持的符号链接或复制安装方式，避免维护两份内容。每个 Skill 的 `SKILL.md` 只使用开放 Agent Skills 标准允许的基础 frontmatter，以保持可移植性。

## 23. 测试

### 23.1 固定课程测试

1. 完整合格课程，应得到“可上传”。
2. 当前样例，应发现视频交互时间超过 MP4 时长。
3. 缺少引用图片。
4. 重复 ID。
5. 路径使用 `../`。
6. HTML 缺少完成消息。
7. HTML 提交结构错误。
8. 视频存在 `needs-timing`。
9. 客观题缺少答案。
10. 原始内容点未处理。
11. AI 新增未经确认的实质结论。

### 23.2 Skill 场景测试

1. 一份 Word，未提视频或 HTML。
2. 多份材料重复或冲突。
3. 输入 HTML 已包含部分互动。
4. 只有课程大纲，细节严重不足。
5. 教师中途改变结构。
6. 没有最终 MP4，先设计视频交互。

测试要验证 AI 是否主动询问复杂媒体、是否保存教师决定、是否阻止未经确认的编造、是否在完成后调用 Review。

## 24. 验证边界

本系统可以验证：

- 结构和字段符合约定。
- 文件引用存在且安全。
- Markdown 与 JSON 一致。
- HTML 具备必要的平台协议。
- 视频时间点在机械上有效。
- 原始材料内容得到可追溯处理。
- 静态教学设计要素完整。

本系统不能仅凭这些检查证明：

- HTML 在所有真实平台 iframe 环境中视觉可靠。
- 视频内容本身事实正确。
- 教学设计一定促进理解或迁移。
- 真实学生达到预期学习效果。

这些更高层结论需要真实平台运行测试、学科审核和学习证据。
