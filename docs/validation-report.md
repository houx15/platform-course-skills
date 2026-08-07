# 平台课程标准化工具包验证报告

日期：2026-08-07

## 设计覆盖

| 设计要求 | 实现 | 自动验证 |
| --- | --- | --- |
| `course.json` 是课程主数据 | `schemas/course.schema.json`、`course_toolkit/course_validation.py` | `tests/test_contracts.py`、`tests/test_course_validation.py` |
| `index.md` 是确定性学生视图 | `course_toolkit/index_renderer.py`、`scripts/render-index.py` | `tests/test_index_renderer.py` |
| 学生内容与作者信息分流 | `.course-work/audience-classification.json`、`validate_learner_facing_course` | 完整分类、重复/遗漏 source ID、设计元数据泄漏测试 |
| 生成前课程设计确认表 | `.course-work/course-storyboard.json/.md`、`scripts/render-course-storyboard.py` | Part/Piece 对账、模态对账、教师确认、生成视图漂移测试 |
| 每个 Part 六维 Review | `.course-work/review-report.json/.md`、`scripts/render-review-report.py` | 缺维度、失败 Part、缺整体检查项和错误“可上传”声明测试 |
| 视频交互 JSON 和 Markdown | `course_toolkit/video_interactions.py`、对应 CLI | `tests/test_video_interactions.py` |
| 不依赖外部工具读取 MP4 时长 | `course_toolkit/mp4.py` | 临时构造最小 MP4，验证时长和越界事件 |
| HTML 平台协议 | `course_toolkit/html_validation.py`、`scripts/validate-html.py` | `tests/test_html_validation.py` |
| DOCX、HTML、Markdown、文本提取 | `course_toolkit/materials.py`、`scripts/extract-materials.py` | `tests/test_materials.py`，包含 DOCX 表格行列定位 |
| 来源覆盖与 AI 新增确认 | `course_toolkit/coverage.py` | 提取清单逐项对账、真实 Block 去向、未确认决定和 unresolved 阻塞测试 |
| 独立上传前 Review | `course_toolkit/package_review.py`、`scripts/validate-course.py` | 完整工作记录与缺失/漂移/不一致测试 |
| ZIP 始终忽略 | 提取器、安装器和 Review | 材料、安装和包 Review 测试 |
| 单一教师入口 | `skills/build-platform-course/` | `tests/test_skill_packages.py` |
| 显式视频/HTML 询问 | 材料分析和主构建 Skills | Skill 场景契约测试 |
| Claude/Codex 双端安装 | `scripts/install-skills.py` | `tests/test_installer.py` |

## `for_test.docx` 端到端结果

### 原材料处理

- DOCX 成功提取 481 个内容点，表格单元格保留 `table/row/cell/paragraph` 坐标，没有展平成普通段落。
- 受众分类：67 个 `student-core`、309 个 `student-evidence`、57 个 `teacher-design`、36 个 `ai-system`、4 个 `reference`、8 个 `proposed-exclusion`。
- 376 个学生内容点映射到真实课程 Block；105 个非学生内容点以测试情境确认的理由保留在作者工作记录或排除。481 个 source ID 在提取、分类和 coverage 中完整对账。

### 新课程结构

- 生成 6 个 Part、12 个 Piece、24 个 Block。
- Block 构成：12 个 `text`、7 个 `singleChoice`、4 个 `fillBlank`、1 个 `interactiveHtml`。
- 每个 Piece 均包含学生行动或学习证据；没有纯文本 Piece。
- 12 个文本 Block 平均 194 字，最长 374 字；旧样例中从 Word 大段复制、表格转项目符号的做法已移除。
- 学生课程中没有“设计总览”“AI 角色”“老师 vs 系统”、作者 coverage 说明或平台实现信息。
- 原 Word 的 FLICC 表、主张库、图表溯源、level/trend 带练、独立证据链和核查射程均转成学生可使用的对照、步骤、交互或评价活动。

### 媒体与资源决定

- 使用一项已确认的城市热岛 HTML 带练；自包含资源、4:3 画布、标准完成按钮和 `INTERACTION_COMPLETE` 1.0 静态合同通过。
- 没有生成图片、流程图、示意图或信息图；课程不引用任何未提供视觉资源。
- 本轮 fixture 明确选择不嵌入长视频，因此上传课程没有 video Block，也不需要 MP4。两份结构化视频交互设计保留在 `.course-work/video-designs/`，事件仍为 `needs-timing`；未来提供 MP4 并嵌入课程时必须重新对齐时间和完整 Review。

### 设计与 Review 表

- `.course-work/course-storyboard.md` 输出 6 Part / 12 Piece 总数，并一行对应一个 Piece，列出阶段目标、学生所见、教学重点、模态、学生行动、完成标准、资源与待确认项。
- `.course-work/review-report.md` 先输出 6 行 Part 逐项 Review，再输出 10 项整体 Review。
- 每个 Part 分别检查教学目标与结构、内容完整性、学生呈现、模态选择、练习与反馈、资源与格式。
- 端到端确定性 Review 返回 `可上传`，无 schema、生成视图、资源路径、HTML、来源覆盖、受众分类、storyboard 或 review-report 错误。

## 发布仓库说明

- 仓库不发布课程样例 MP4；工具不会生成、剪辑、转码或修改 MP4。
- 教师材料、ZIP、端到端生成物和浏览器截图不属于安装包。
- 安装器始终忽略 ZIP。

## 验证边界

- 端到端 fixture 的“教师确认”是测试输入，用于验证完整流程可以产出标准仓库，不代表真实课程教师已经确认内容。
- 来源覆盖与 Part Review 能验证结构化证据、课程呈现和记录完整性，不能独立证明气候科学事实、引用准确性或真实学生学习效果。
- HTML 已通过静态合同；旧版样例曾完成 headless Chromium 桌面/移动与完成消息测试，本次内容未在真实平台 iframe 重新验证。
- DOCX 已渲染为 11 页并逐页检查表格与分区结构；当前 LibreOffice 环境缺少原文所用中文字体，渲染图中的部分中文字形不可见，因此文字内容以 OOXML 提取结果为准。
- 项目要求在主线程顺序执行，本次没有使用子代理做 Skill 前向对话测试。实际教师使用后的对话表现仍需持续收集。
