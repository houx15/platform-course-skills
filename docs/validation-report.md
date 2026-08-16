# 平台课程标准化工具包验证报告

日期：2026-08-12

## 2026-08-16：CourseDefinition 2.0 静态与素材验证迭代

### 本轮范围

- 分支：`dev`；仅本地提交，未 push，未上传 OSS，未调用课程接口。
- 新增确定性 CourseDefinition 2.0 包验证器与 `validate-course-v2.py`。验证从当前 G5 证据开始，覆盖共享 Zod contract、素材清单与安全相对路径、文件存在性/大小/SHA-256、PDF 头尾、MP4/H.264/AAC/faststart/真实时长、视频互动 1.1 cue、WEBVTT、HTML `mind-course-interaction` 1.0 握手与完成学习证据，以及固定课程完整性 warning。
- 成功或仅有 warning 时写入 `.course-work/course-validation-report.json`；阻断结果单独写入 `.course-work/course-validation-attempt.json`，不会把上一份成功证据冒充为当前失败结果。
- G6 现在核验 definition、validation report、验证器依赖代码、asset set 与每个素材的当前哈希。素材无论位于 `course/assets/`、`assets/` 或 `interactions/`，内容变化、缺失或变成 symlink 都会使 G6 及下游失效。
- 原始检查码保留在 validation report；工作流只登记四类稳定问题。包错误是不可接受的 blocker；Slice 密度 warning 不要求确认；预计时间和媒体 warning 必须由教师明确给出理由后通过 `accept-warning` 接受。
- CourseDefinition 2.0 HTML 校验使用学生 renderer 已实现的 envelope、session token 回显与 ready/completed 类型；本地进一步要求 completed payload 包含稳定 `interactionId` 和 JSON-compatible `evidence`。学生端是否持久化该 payload 仍属于 G7 runtime 集成边界。

### 自动验证

| 验证 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests -q` | 297 项通过，0 failure，0 error |
| G6/包验证/issue/CLI 聚焦测试 | 77 项通过 |
| `pnpm --filter @mind-imprint/course-contract test` | 13 个 test file、56 项测试通过 |
| `pnpm --filter @mind-imprint/course-contract typecheck` | 通过 |
| `python scripts/check-course-contract-sync.py --upstream /Users/houyuxin/08Coding/mind-imprint --json` | `mismatches: []`；学生端当前 HEAD 为 `5624178c91c83d61709af306818c6b88756a2c65`，快照 commit 较早但 contract 源码无漂移 |
| 全部 `schemas/*.json` | `python -m json.tool` 语法通过 |

### 真实旧课程 G6 演练

使用原 6 Part / 13 Slice / 27 Block fixture，在临时目录完成显式迁移确认、两次确定性编译与两次完整验证。PDF 仅复制原始字节；旧 HTML 不修改 fixture，只在临时目录换成 CourseDefinition 2.0 协议测试文件。

结果：2 个素材，validation 状态 `clear`，0 issue，0 warning；G6 能复验当前 asset-set 与逐素材哈希。

- validation report：`aea48de252a18643ef9da09e98929586c9417f1c28d380a58e1aa97edbdecb2d`
- asset set：`394b65715385a91e458a4d8e1eb340bb0ce03436d0aa603f44c1f5a9976ef7ef`
- validator code：`6e74451e292eb843a95f5c2f9dc657bcd0a53d3c581b6840e00cd57f8544c8bc`

### 当前明确边界

- 本地流程现已完成至 G6：Blueprint、CourseDefinition 2.0 编译、共享 contract、静态/素材/媒体/HTML 验证与可失效证据门均可使用。
- G7 仍依赖学生 renderer、真实浏览器预览和结构化批注 UI。静态报告不能证明布局、自动播放、iframe、视频弹窗互动或完成事件在学生端真实运行。
- G8 需要基于当前 preview hashes 与批注的独立终审；在 G7 尚未接入时不得伪造完成。
- G9/G10 的 OSS 去重上传、稳定远端课程身份、create/update dry run、真实课程 POST、幂等重试和远端回读仍未实现。本轮没有使用凭证或发生任何外部 mutation。

## 2026-08-16：CourseBlueprint 与 CourseDefinition 2.0 编译迭代

### 本轮范围

- 分支：`dev`；仅本地提交，未 push，未上传 OSS，未调用课程接口。
- 将学生端 `@mind-imprint/course-contract` 以可核验快照纳入工具包。快照对应学生端提交 `df36a8ecd1b30f28c27789fcf02e898b5bee6e21`；学生端仓库后来继续前进，但 contract 的全部 `src/**/*.ts` 字节哈希无漂移。
- 新增 CourseBlueprint 1.0。`.course-work/course-blueprint.json` 是作者态事实源；它保存完整 runtime-shaped course、教师审批决定、来源映射和迁移假设。
- 新增 schemaVersion 1.1 迁移器。Piece 按一对一规则变为 Slice，七种 Block 转成 2.0 形状，legacy `blocking` 转成显式 Workflow；迁移器记录布局、工作流、预计时间、个性化、目标对齐和媒体默认假设，且永远不会沿用旧审批。
- 新增确定性编译器。它只从已确认 Blueprint 生成 `course/course.json`、runtime source map 和 compilation report；学生端共享 Zod、引用校验和 Workflow 校验是唯一运行时 contract gate。
- 新增原子编译 CLI 与 G5 证据门。三项输出必须来自同一次编译；Blueprint、definition、source map、report、编译器代码或 contract 快照任一不匹配都会阻止或失效 G5。失败重编译保留上一套完整输出，模拟中途替换失败可回滚。

### 自动验证

| 验证 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests -q` | 252 项通过，0 failure，0 error |
| `pnpm --filter @mind-imprint/course-contract test` | 13 个 test file、56 项测试通过 |
| `pnpm --filter @mind-imprint/course-contract typecheck` | 通过 |
| `python scripts/check-course-contract-sync.py --upstream /Users/houyuxin/08Coding/mind-imprint --json` | `mismatches: []`；仅仓库 HEAD 比快照更新 |
| Blueprint 编译复现 | frozen CourseDefinition 与 source map 连续两次字节一致 |
| 编译输出故障注入 | 第二项 final replace 失败后，三项旧输出全部恢复且无 `.tmp`/`.bak` 遗留 |

### 真实旧课程迁移演练

使用 `e2e/for-test-course/course/course.json` 与 `.course-work/course-storyboard.json` 在临时目录演练：

1. 导入得到未确认 Blueprint，并记录 5 项迁移假设；
2. 用 context hash 新建并确认 `decision-legacy-two-migration`，确认内容精确包含当次 assumption IDs；
3. 仅在该决定确认后写入 Blueprint approval；
4. 连续编译两次，并再次通过共享学生端 contract。

结果为 6 个 Part、13 个 Slice、27 个 Block、2 个本地素材路径。确定性哈希如下：

- Blueprint：`2da724d90f9c9f4ec54804a43f63132ede5d560966a7418b8b9af8c758435204`
- CourseDefinition：`eabdc283ce9824a12201c3f6331083fb2e5862bfb46aeeb6286526174060a131`
- runtime source map：`2d624b51bdd532580e4c4d1fe68fdd4353c03129cb13aaf93764cc3dfe5ec543`

### 当轮边界（已由上方 G6 迭代更新）

- 当时已实现 CourseDefinition 2.0 的生成、共享 contract 校验、来源映射、原子输出和 G5 当前证据检查；上方迭代现已补齐 G6。
- 现有 `review-platform-course` 仍以 legacy 1.1 为输入，不能用于认证 2.0；CourseDefinition 2.0 改由 `validate-course-v2.py` 和 G6 证据门认证。
- 学生 renderer、真实 browser preview、布局/媒体运行时检查和预览批注 UI 尚未接入，因此不得完成 G7 或把静态文件称为学生端一致预览。
- OSS 上传、素材哈希去重、稳定远端课程身份、create/update dry run、真实 course POST 与远端回读尚未实现。G10 仍只能由未来的真实发布适配器完成。
- 本地 compile、validate、review 或 preview 请求均不授权外部写入；当前迭代没有使用任何凭证或外部 mutation。

## 2026-08-16：课程生产 Workflow 迭代一

### 本轮范围

- 分支：`dev`
- 实施提交范围：`66e707c` 至 `c2082b2`
- 已实现：原子 JSON 写入、版本化问题代码表、问题存储、教师决定存储、G0–G10 会话状态机、路径/哈希核对、定向失效、统一 CLI，以及 `build-platform-course` 单一教师入口的恢复与门禁规则。
- 所有工作均为本地操作；本轮没有 push、OSS 上传、课程 POST 或其他外部修改。

### 自动验证

| 验证 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests -q` | 199 项通过，0 failure，0 error |
| `python scripts/validate-course.py tests/fixtures/valid-course --json` | `uploadable`；0 issue，0 warning |
| 新增 Workflow/issue/decision/CLI/Skill 聚焦测试 | 52 项通过 |
| 三份新增 JSON Schema 语法检查 | `python -m json.tool` 通过 |

### 手工恢复与失效演练

在临时课程根中执行：

1. `init` 注册稳定的 `courseLocalId` 和 `materials/source.md`；
2. `complete-gate ... G0` 后进入 `material-review`；
3. 用不同内容替换已登记材料；
4. `reconcile` 检测到 `materials/` 哈希变化，保持 G0，返回 G1 对应的 `material-review`；
5. 生成 `workflow-artifact-changed` warning，`gateId` 为 G1，下一动作为 `complete G1`。

这证明恢复过程不会把材料变化误判成已完成，也不会无条件重启到 G0。

### 当轮边界（已由上方迭代二更新）

- 截至迭代一，生成链仍是 legacy `schemaVersion: 1.1`；Blueprint、CourseDefinition 2.0 编译器和 runtime source map 当时尚未实现，现已由上方迭代二补齐。
- G0–G10 内核目前验证顺序、活动 blocker 和待确认决定。各 gate 的完整确定性证据适配器会随编译、增强校验、预览、批注和发布迭代接入；现阶段不得仅因 CLI 可以顺序记录 gate 就声称对应外部能力已完成。
- 尚未实现学生端 renderer 预览、真实浏览器验证、批注 UI 或 TTS。静态 `index.md` 不能证明 G7 通过；本地 CLI 也不能手工完成 G10。
- 尚未实现 CourseDefinition 2.0 的增强格式/完整性检查、HTML runtime bridge 全量检查、预览批注应用协议、asset manifest、publish state、OSS 去重上传或课程 create/update 接口。
- G9 的 dry run、稳定远端身份、防重复创建、幂等重试和远端回读将在 mockable publication 迭代实现；真实 OSS 与学生端 API 仍需后续适配器和凭证。
- 本轮问题代码表只包含 Workflow 基础代码。编译、contract、asset、preview、review 与 publication 的专用代码会在对应迭代加入同一注册表。

## 设计覆盖

| 设计要求 | 实现 | 自动验证 |
| --- | --- | --- |
| `course.json` 是课程主数据 | `schemas/course.schema.json`、`course_toolkit/course_validation.py` | `tests/test_contracts.py`、`tests/test_course_validation.py` |
| `index.md` 是确定性学生视图 | `course_toolkit/index_renderer.py`、`scripts/render-index.py` | `tests/test_index_renderer.py` |
| 每门课具有课程开场与结课总结 | `course.introduction`、`course.conclusion`、固定“开始学习”动作 | 1.1 必填字段、列表上下限、首尾顺序、旧 1.0 阻塞迁移测试 |
| 课程目标对齐真实学习过程 | `courseFrame.objectiveAlignment` | 目标唯一对齐、真实 Part、真实学习证据 Block 和静态内容不能冒充证据的测试 |
| 完整 PDF 原生呈现 | `pdf` Block、`assets/pdfs/`、`course_toolkit/pdf_validation.py` | 扩展名、安全路径、`%PDF-`、`%%EOF`、`invalid-pdf-header`、生成链接和阻塞 Review 测试 |
| 学生内容与作者信息分流 | `.course-work/audience-classification.json`、`validate_learner_facing_course` | 完整分类、重复/遗漏 source ID、设计元数据泄漏测试 |
| 生成前课程设计确认表 | `.course-work/course-storyboard.json/.md`、`scripts/render-course-storyboard.py` | Part/Piece 对账、模态对账、教师确认、生成视图漂移测试 |
| 每个 Part 六维 Review | `.course-work/review-report.json/.md`、`scripts/render-review-report.py` | 缺维度、失败 Part、缺整体检查项和错误“可上传”声明测试 |
| 视频交互 JSON、Markdown 与媒体规范 | `course_toolkit/video_interactions.py`、对应 CLI | H.264/AAC/faststart 阻断、10 分钟交互提醒、500 MiB 文件提醒、时长与事件测试 |
| 不依赖外部工具检查 MP4 | `course_toolkit/mp4.py` | 临时构造最小 MP4，验证封装、轨道编码、faststart、时长和越界事件 |
| HTML 平台协议与字号 | `course_toolkit/html_validation.py`、`scripts/validate-html.py` | 16px 正文/控件、14px 辅助文字、安全 clamp/rem 和不可验证单位测试 |
| HTML 确定性检查报告 | `course_toolkit/html_reports.py`、`scripts/generate-html-report.py` | JSON/Markdown 生成、SHA-256 新鲜度、缺失/过期报告阻断完整 Review 测试 |
| DOCX、HTML、Markdown、文本提取 | `course_toolkit/materials.py`、`scripts/extract-materials.py` | `tests/test_materials.py`，包含 DOCX 表格行列定位 |
| 来源覆盖与 AI 新增确认 | `course_toolkit/coverage.py` | 提取清单逐项对账、真实 Block 去向、未确认决定和 unresolved 阻塞测试 |
| 独立上传前 Review | `course_toolkit/package_review.py`、`scripts/validate-course.py` | 完整工作记录与缺失/漂移/不一致测试 |
| ZIP 始终忽略 | 提取器、安装器和 Review | 材料、安装和包 Review 测试 |
| 单一教师入口 | `skills/build-platform-course/` | `tests/test_skill_packages.py` |
| 显式视频/HTML 询问与 PDF 双重用途识别 | 材料分析和主构建 Skills | Skill 场景契约测试 |
| Claude/Codex 双端安装 | `scripts/install-skills.py` | `tests/test_installer.py` |

## `for_test.docx` 端到端结果

### 原材料处理

- DOCX 成功提取 481 个内容点，表格单元格保留 `table/row/cell/paragraph` 坐标，没有展平成普通段落。
- 受众分类：67 个 `student-core`、309 个 `student-evidence`、57 个 `teacher-design`、36 个 `ai-system`、4 个 `reference`、8 个 `proposed-exclusion`。
- 376 个学生内容点映射到真实课程 Block；105 个非学生内容点以测试情境确认的理由保留在作者工作记录或排除。481 个 source ID 在提取、分类和 coverage 中完整对账。

### 新课程结构

- 生成 6 个 Part、13 个 Piece、27 个 Block。
- `course.json` 使用 1.1；课程第一幕包含学生介绍、3 条目标、4 项关键点和固定“开始学习”动作，全部 Part 后包含总结、takeaway 与迁移场景。
- Block 构成：13 个 `text`、7 个 `singleChoice`、5 个 `fillBlank`、1 个 `pdf`、1 个 `interactiveHtml`。
- 每个 Piece 均包含学生行动或学习证据；没有纯文本 Piece。
- 13 个文本 Block 平均 185 字，最长 374 字；旧样例中从 Word 大段复制、表格转项目符号的做法已移除。
- 学生课程中没有“设计总览”“AI 角色”“老师 vs 系统”、作者 coverage 说明或平台实现信息。
- 原 Word 的 FLICC 表、主张库、图表溯源、level/trend 带练、独立证据链和核查射程均转成学生可使用的对照、步骤、交互或评价活动。

### 媒体与资源决定

- 使用一项已确认的城市热岛 HTML 带练；自包含资源、4:3 画布、标准完成按钮、16px 字号下限和 `INTERACTION_COMPLETE` 1.0 静态合同通过，并生成匹配当前文件 SHA-256 的 JSON/Markdown 报告。
- 样例课程增加一个完整 PDF Piece，使用明确标注为结构测试材料的文件；它用于验证 `pdf` Block、内嵌/下载链接和 Review，不冒充材料提到的真实论文。
- 没有生成图片、流程图、示意图或信息图；课程不引用任何未提供视觉资源。
- 本轮 fixture 明确选择不嵌入长视频，因此上传课程没有 video Block，也不需要 MP4。两份结构化视频交互设计保留在 `.course-work/video-designs/`，事件仍为 `needs-timing`；未来提供 MP4 并嵌入课程时必须重新对齐时间和完整 Review。

### 设计与 Review 表

- `.course-work/course-storyboard.md` 先输出课程首尾设计表，再输出 6 Part / 13 Piece 总数；Part/Piece 表一行对应一个 Piece，列出阶段目标、学生所见、教学重点、模态、学生行动、完成标准、资源与待确认项。
- 三条课程目标分别对齐真实 Part 和可留下结果的选择、填空或交互 Block；PDF、图片和静态文字没有被当作学习证据。
- `.course-work/review-report.md` 先输出 6 行 Part 逐项 Review，再输出 13 项整体 Review（包含 `courseIntroduction`、`courseConclusion` 和 `pdf`）。
- 每个 Part 分别检查教学目标与结构、内容完整性、学生呈现、模态选择、练习与反馈、资源与格式。
- 端到端确定性 Review 返回 `可上传`，无 schema、生成视图、资源路径、HTML、来源覆盖、受众分类、storyboard 或 review-report 错误。
- 仓库完整自动测试共 154 项通过；标准 fixture、本地样例和 `for_test.docx` 端到端课程均返回 `可上传`。

## 发布仓库说明

- 仓库不发布课程样例 MP4；工具包本身不会生成、剪辑、转码或修改 MP4。构建 Skill 在发现不兼容视频时会给出隔离的新会话 prompt；任何 subagent 转换都必须先获得教师对输入和新输出路径的明确授权。
- 仓库只发布明确标注的 PDF 结构测试材料，不下载或伪造老师材料提到的论文原文。
- 教师材料、ZIP、端到端生成物和浏览器截图不属于安装包。
- 安装器始终忽略 ZIP。

## 验证边界

- 端到端 fixture 的“教师确认”是测试输入，用于验证完整流程可以产出标准仓库，不代表真实课程教师已经确认内容。
- 来源覆盖与 Part Review 能验证结构化证据、课程呈现和记录完整性，不能独立证明气候科学事实、引用准确性或真实学生学习效果。
- HTML 已通过静态合同和报告新鲜度检查；旧版样例曾完成 headless Chromium 桌面/移动与完成消息测试，本次内容未在真实平台 iframe 重新验证。
- PDF 头尾与本地渲染检查不能证明真实平台的内嵌阅读、逐页兼容性、出版版本权威性或学生实际阅读完成度。
- DOCX 已渲染为 11 页并逐页检查表格与分区结构；当前 LibreOffice 环境缺少原文所用中文字体，渲染图中的部分中文字形不可见，因此文字内容以 OOXML 提取结果为准。
- 项目要求在主线程顺序执行，本次没有使用子代理做 Skill 前向对话测试。实际教师使用后的对话表现仍需持续收集。
