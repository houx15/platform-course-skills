# 平台课程生产工具包

这套 Skills 帮助内部教师与 Codex、Claude 等 Agent，把 Word、Markdown、PDF、视频、HTML、图片及零散教学材料，逐步整理成可预览、可批注、可检查并可提交到 Mind Imprint 学生端的 CourseDefinition 2.0 课程。

教师只使用一个主入口：`build-platform-course`。材料分析、课程结构补全、媒体检查、真实渲染预览、批注修改、独立终审和发布都由主入口按当前阶段调用，不要求教师理解 JSON、validator 或内部 Skill 分工。

## 一句话安装

老师在 Codex 中发送：

```text
帮我安装这套 Skills：https://github.com/houx15/platform-course-skills
```

安装完成后的下一轮对话发送：

```text
使用 $build-platform-course，把我的已有材料整理成可预览的平台课程。
```

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
