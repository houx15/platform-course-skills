# 平台课程生产工具包

这套 Skills 帮助内部教师与 Codex、Claude 等 Agent，把 Word、Markdown、PDF、视频、HTML、图片及零散教学材料，逐步整理成可预览、可批注、可检查并可提交到 Mind Imprint 学生端的 CourseDefinition 2.0 课程。

教师只使用一个主入口：`build-platform-course`。材料分析、课程结构补全、媒体检查、真实渲染预览、批注修改、独立终审和发布都由主入口按当前阶段调用，不要求教师理解 JSON、validator 或内部 Skill 分工。

## 老师如何使用

老师只需要准备材料、回答教学判断、查看预览并批准最终提交。课程目录、JSON、格式检查、预览服务和发布操作由 Agent 处理。

老师只需要用中文自然交流，不需要把批注或确认翻译成英文。Agent 应使用中文说明材料判断、设计方案、检查结果和发布风险；只有稳定 ID、文件路径、Contract 字段或排错命令等必要技术内容保留原文。

### 第一步：准备课程文件夹

为每门课准备一个独立文件夹，把现有材料原样放进去。Word、Markdown、文本、PDF、PPT、图片、MP4、字幕和独立 HTML 都可以混合存在，不需要提前整理成统一格式。

建议增加一个 `index.md`，简单写清楚：

- 这门课大概讲什么；
- 各份材料是什么、希望怎样使用；
- 已知的学生对象、时长或教学目标；
- 哪些原文、图片、视频或互动必须保留；
- 暂时拿不准的问题。

这份说明不需要完整。Skill 会继续盘点材料并向老师确认。不要只提供 ZIP；ZIP 不参与课程分析。完整 PDF、视频和 HTML 应保留为独立文件。

示例目录：

```text
my-course/
├── index.md
├── lesson-notes.docx
├── reference-report.pdf
├── demonstration.mp4
├── interaction.html
└── images/
```

### 第二步：安装或更新 Skills

在 Codex 中发送：

```text
帮我安装这套 Skills：https://github.com/houx15/platform-course-skills
```

如果已经安装过、现在需要更新，发送：

```text
请把这套课程 Skills 更新到最新版本：https://github.com/houx15/platform-course-skills
```

安装或更新完成后，开启一个新任务，使 Codex 载入最新版 Skills。

### 第三步：开始一门新课程

在课程文件夹中打开 Codex，或者在消息中提供课程文件夹和入口材料的绝对路径。然后发送：

```text
使用 $build-platform-course，把下面的已有材料整理成一门完整、可预览的平台课程。

课程文件夹：
<课程文件夹的绝对路径>

入口材料：
<index.md 或主要材料的绝对路径>

请先盘点材料和需要我决定的问题，再逐步和我确认。未经我明确批准，不要上传或提交课程。
```

如果没有 `index.md`，列出主要文件即可。不要让 Agent 猜测课程文件夹；路径必须明确。

### 第四步：完成教学确认

Agent 会分阶段和老师确认，不会直接把零散材料变成最终课程。老师主要需要判断：

1. **材料怎么使用**：哪些给学生看，哪些只是教师参考；是否需要完整 PDF；是否有长视频或独立 HTML 互动。
2. **课程要达到什么结果**：学生对象、前置知识、课程目的、学习目标、预计时长和评价方式。
3. **学生怎样学习**：课程开场和结尾、Part/Slice 顺序、每一屏看到什么、做什么、怎样完成。
4. **复杂互动是否正确**：视频何时暂停、弹出什么问题；HTML 完成时提交什么学习数据；答案、反馈和必做规则是否符合教学意图。

Agent 会先展示课程首尾设计，再展示完整 Part/Slice 表。一行代表学生看到的一屏。老师应重点检查：

- 顺序是否符合自己的教学思路；
- 每屏内容是否过多；
- 图片、PDF、视频、HTML 或题目是否用在合适的位置；
- 学生行动与完成条件是否明确；
- AI 补充的解释、答案、反馈和总结是否准确。

可以直接用自然语言修改，例如：

```text
第二部分的概念解释太早了。先让学生观察视频，再总结规律。

这一页不要放完整 PDF，只展示两张关键图片；PDF 放到下一页供学生查证。

这道题不应该答错一次就通过，第二次错误后再显示提示。
```

涉及教学含义、答案、完成规则、媒体行为或课程结构的修改，Agent 会再次向老师确认。确认完整设计后，它才会生成学生端课程并进行格式检查。

### 第五步：处理检查结果

Agent 会检查课程结构、每页 layout 和 workflow，以及 PDF、视频、字幕、HTML、互动协议和所有素材路径。

- **必须修复的问题**会阻止预览或提交；
- **需要老师判断的提醒**会说明影响，请老师选择是否接受；
- **页面内容较密等普通建议**会展示，但不会强迫老师确认。

老师不需要修改 JSON 或执行检查命令。提供缺失材料、回答教学问题，或者允许 Agent 对已经说明的机械问题进行修复即可。视频格式不兼容时，Skill 不会覆盖原视频；它会提供在独立任务中生成兼容副本的安全做法。

### 第六步：在浏览器中预览和批注

检查通过后，Agent 会打开本机预览链接。这里使用学生端的真实课程 renderer，但开场、结尾和逐页讲解在本地预览中可以静音。

右侧“课程批注”默认收起为 46px，点击后展开为 330px，与学生端“问印记”侧栏的两种宽度一致。检查课程排版时先收起侧栏；需要留言时再展开，这样可以同时观察学生打开和收起侧栏时的真实比例。

老师需要：

1. 从课程开场开始；
2. 访问每一个 Slice；
3. 实际操作相关视频弹题、HTML、PDF、答题和翻页；
4. 检查全屏、左右分栏和上下分栏是否清楚；
5. 在右侧批注栏选择对应的 Slice、Block、图片或 workflow Step，写下具体意见；
6. 只有在所有页面和关键互动都检查完后，才点击“确认我已完整审查”。

一条有用的批注应同时说明问题和期望，例如：

```text
这一页右侧图片太小，无法比较两种结构。希望改成上下布局，图片在上、总结在下。

视频在 01:24 出题太早，学生还没有看到完整操作。请把问题移到操作结束后。

完成 HTML 活动后页面没有继续，像是运行错误，不是课程文案问题。
```

保存批注后，在 Codex 中发送：

```text
请处理我刚才在预览中留下的全部批注。先告诉我哪些可以直接修改，哪些会改变教学含义，哪些属于学生端运行问题。
```

Agent 会把文案修正、语义修改和 renderer bug 分开处理。需要改变教学含义的方案必须再次得到老师批准。修改后必须重新生成、重新检查并打开新预览；旧预览不能证明新版本已经通过。

### 第七步：完成终审

当新预览没有未处理批注或运行错误，老师再次逐页检查并点击完成。Agent 随后进行一次独立终审，最终给出：

- `可上传`；或
- `缺少必要材料，暂不可上传`。

“可上传”只表示本地课程、素材和预览证据已经完整，不代表课程已经上传。

### 第八步：保存到学生端或正式发布

需要提交时，仍然只调用主入口：

```text
请为当前课程准备一次学生端发布计划，只展示将创建还是更新、需要上传和复用的素材数量以及风险。在我明确批准以前不要执行。
```

老师可以选择：

- `save-preview`：保存到学生端预览状态，适合第一次联调；
- `publish`：正式发布，并触发学生端 ship/TTS。

Agent 会先展示精确 dry run。确认课程 ID、创建或更新、素材数量和风险后，老师再明确批准，例如：

```text
我批准刚才这份发布计划。批准理由：课程已经完成预览和终审，可以保存到学生端预览状态。
```

任何课程内容、素材、远端状态或发布选项变化都会使旧批准失效。修改同一门课时始终使用相同课程 ID；未改变的素材会根据相同课程 ID、相对路径和文件哈希复用。

`OSS_ADMIN_KEY` 只应存在于启动 Agent 的进程环境中。不要把它粘贴到对话、课程材料、命令参数、`.course-work` 或 Git。

### 继续上一次工作

课程进度保存在课程文件夹的 `.course-work/` 中。重新打开课程后发送：

```text
使用 $build-platform-course，继续处理这门课程：
<课程文件夹的绝对路径>

请先恢复已有进度，告诉我上次停在哪一步、有哪些未解决问题和下一项需要我决定的事情。不要重新开始，也不要上传。
```

不要删除 `.course-work/` 来“重新生成”。材料、设计或素材发生变化时，Skill 会只让受影响的后续检查重新执行。

### 老师不需要做的事情

- 不需要阅读或手工修改 `course.json`；
- 不需要选择内部子 Skill；
- 不需要自己运行 validator、预览服务器或上传脚本；
- 不需要在学生端创建教师账号；
- 不需要在每次修改后重新创建课程；
- 不要用“页面能打开”代替完整的逐页和互动检查。

## 安装协议与维护者说明

### Codex 安装协议

以下内容供收到安装请求的 AI 执行。不要要求老师自己打开终端或选择内部 Skill。

1. 这是包含 9 个课程 Skills 和一个共用运行时的工具包。不要把仓库根目录当作单个 Skill，也不要只安装其中一个子目录。
2. 使用用户提供的 HTTPS 仓库地址，将仓库克隆到不会覆盖课程材料的临时位置。
3. 在仓库根目录运行：

   ```bash
   python3 scripts/install-skills.py --target codex
   ```

4. 确认安装目录包含：

   - `build-platform-course`
   - `analyze-course-materials`
   - `design-course-blueprint`
   - `design-course-html`
   - `design-video-interactions`
   - `preview-platform-course`
   - `apply-preview-feedback`
   - `review-platform-course`
   - `publish-platform-course`
   - `_course-toolkit`

5. 不删除其他 Skills。目标已存在时，只有用户明确要求更新才使用 `--replace`。
6. 安装后告知教师下一轮可调用 `$build-platform-course`，不要在安装请求中擅自开始处理课程。

## 手动安装

要求 Python 3.9 或更高版本；预览与共享 contract/renderer 还使用工具包内固定版本的 Node 运行时产物。

```bash
git clone https://github.com/houx15/platform-course-skills.git
cd platform-course-skills
python3 scripts/install-skills.py --target codex
```

同时安装到 Codex 与 Claude Code：

```bash
python3 scripts/install-skills.py --target both
```

更新已安装版本：

```bash
git pull
python3 scripts/install-skills.py --target both --replace
```

## 教师生产流程

整个过程由 `.course-work/session.json` 持久化，并通过 G0–G10 质量门推进：

1. 安全确认课程目录、身份与输入材料。
2. 盘点材料，确认学生内容、教师设计、参考材料、完整 PDF，以及是否需要视频和独立 HTML。
3. 确认受众、前置知识、课程目的、学习目标、时长和评价意图。
4. 先展示课程首尾设计表，再展示完整 Part/Slice 表；一行对应一个 Slice。教师确认整体设计后才生成。
5. AI 补齐每个 Slice 的明确 layout、Blocks、narrations、workflow、导航和完成规则。
6. 从 `.course-work/course-blueprint.json` 确定性编译 `course/course.json`，不得直接修改生成文件。
7. 使用学生端共享 Zod contract 和专项检查器验证 CourseDefinition 2.0、PDF、MP4、字幕、视频交互和 HTML 协议。
8. 用真实学生端 renderer 在本机预览。教师逐页检查并在页面侧栏写结构化批注。
9. `apply-preview-feedback` 将批注分为文案机械修改、需要明确确认的语义修改和学生端 runtime bug；修改 Blueprint 后重新编译、校验和预览。
10. 独立终审通过后，才准备精确发布 dry run。教师确认后上传必要 OSS 素材，保存同一稳定 slug 的课程，并按要求 ship。

任何输入、Blueprint、素材、renderer、批注或终审证据变化，都会使相应下游证据失效。文件存在不代表质量门已经通过。

## CourseDefinition 2.0 与学生体验

课程打开后先展示可根据学生历史实时生成的开场；静态 fallback 说明学什么、预计用时，并提供“开始学习”。正文由 Part 和一屏一个的 Slice 组成。每个 Slice 使用学生端支持的预定义 layout，包括全屏、左右分栏与上下分栏；页面中的素材、讲解、等待、交互和翻页由显式 workflow 驱动。

支持的 Block 包括文本、图片组、PDF、视频、交互 HTML、填空和单选。一个 Slice 应保持视觉可读，素材过多时拆页。课程结尾由学生数据与预先准备的 fallback 总结共同支持，静态文本不得声称某个学生已经掌握内容。

开场、结尾与逐页 narration 的音频路径属于学生端 ship 阶段生成的 TTS 目标，不要求教师本地生成，也不会作为老师素材上传。当前本地预览使用 fallback 文本且静音。

## 媒体与交互检查

- `pdf` Block 必须保留老师确认的原始 PDF 字节，并检查扩展名、文件头、EOF、路径安全与真实 renderer 行为。
- 视频必须是 MP4、H.264、`yuv420p`、faststart；存在音轨时使用 AAC。交互文件会检查时间范围、自动暂停、必做题和完成规则。
- HTML 在 iframe 中遵守 renderer 支持的消息协议。完成时必须提交规定的学生学习数据；自动播放音乐仍受浏览器 autoplay 策略约束，并需要在真实预览中验证。
- WEBVTT、JSON、HTML、图片、PDF 与视频均按课程内相对路径管理。

不兼容视频不得覆盖原文件。应在独立会话中用 `ffmpeg -n` 生成新副本，再重新对齐时间点并验证。

## 预览、批注与修改

`preview-platform-course` 只绑定 `127.0.0.1`，使用真实学生端 renderer、内存 session adapter 和本地素材解析。批注 UI 位于 renderer 外部，并绑定 Course、Part、Slice、Block、图片 item 或 workflow Step 的稳定 ID；不会把 CSS selector、坐标或 DOM 结构当作修改目标。

完成预览要求教师访问每个 Slice、检查相关交互与分支、处理 runtime error，并明确点击完成。修改后必须重新生成当前 hash 对应的预览证据。打开页面或生成截图都不能代替这一过程。

## 发布与安全边界

发布只由 `publish-platform-course` 执行，并要求当前 G8 终审证据与一份教师明确批准的 production dry run。

- 课程身份使用与 `course.id` 相同的稳定 slug；修改同一门课不会创建新课程。
- 素材使用 `courses/<slug>/<relativePath>` 的确定路径。
- 本地复用证明必须同时匹配 slug、相对路径和 SHA-256，避免重复上传；服务端当前没有素材 checksum/existence 查询，因此不会把未验证的远端对象当作已存在。
- 创建和更新都使用同一个 slug-keyed definition PUT；发布后再调用 ship 并读取课程状态和完整 definition 验证。
- published 课程的 definition PUT 会先改变线上字节，ship 会重新生成 TTS；dry run 会明确提示这两个风险。
- 接口为 last-writer-wins，当前没有 revision/optimistic concurrency。远端状态在批准后变化会阻止执行。

`OSS_ADMIN_KEY` 只能通过进程环境变量提供。工具不会把它写入参数、课程文件、`.course-work`、Git 或普通输出；Bearer 只发送给学生端管理 API，不会发送到预签名 OSS URL。构建、检查、预览或批注请求都不构成上传或发布授权。

## 本地目录

- `course/course.json`：确定性生成的学生端 CourseDefinition 2.0。
- `course/assets/`、`course/interactions/`：实际交付素材。
- `.course-work/`：Blueprint、决策、issues、校验、预览、批注、终审与发布恢复状态，不提交给学生端。
- `skills/`：教师主入口与内部专用 Skills。
- `course_toolkit/`、`scripts/`：共享 contract/renderer、确定性检查与命令行工具。

ZIP 不参与材料分析或发布。原始材料留在教师仓库内，工具只写课程目录、`.course-work` 与明确的生成文件。

## 管理员验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate-course-v2.py COURSE_ROOT --json
python3 scripts/review-course-v2.py COURSE_ROOT --json
```

真实预览：

```bash
python3 scripts/preview-course.py COURSE_ROOT
```

发布状态、preflight 和 execute 的详细命令见 `skills/publish-platform-course/SKILL.md`。真实发布会改变生产环境，不能用普通测试请求代替教师批准。
