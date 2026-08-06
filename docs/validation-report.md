# 平台课程标准化工具包验证报告

日期：2026-08-06

## 设计覆盖

| 设计要求 | 实现 | 自动验证 |
|---|---|---|
| `course.json` 是课程主数据 | `schemas/course.schema.json`、`course_toolkit/course_validation.py` | `tests/test_contracts.py`、`tests/test_course_validation.py` |
| `index.md` 是确定性视图 | `course_toolkit/index_renderer.py`、`scripts/render-index.py` | `tests/test_index_renderer.py` |
| 视频交互 JSON 和 Markdown | `course_toolkit/video_interactions.py`、对应 CLI | `tests/test_video_interactions.py` |
| 不依赖外部工具读取 MP4 时长 | `course_toolkit/mp4.py` | 测试在临时目录动态构造最小 MP4，并验证时长与越界事件 |
| HTML 平台协议 | `course_toolkit/html_validation.py`、`scripts/validate-html.py` | `tests/test_html_validation.py` |
| DOCX、HTML、Markdown、文本提取 | `course_toolkit/materials.py`、`scripts/extract-materials.py` | `tests/test_materials.py`，包含 DOCX 表格行列定位 |
| 来源覆盖与 AI 新增确认 | `course_toolkit/coverage.py` | 提取清单逐项对账、真实 Block 去向、未确认决定和 unresolved 阻塞测试 |
| 独立上传前 Review | `course_toolkit/package_review.py`、`scripts/validate-course.py` | `tests/test_package_review.py` |
| ZIP 始终忽略 | 提取器、安装器和 Review | 材料、安装和包 Review 测试 |
| 单一教师入口 | `skills/build-platform-course/` | `tests/test_skill_packages.py` |
| 显式视频/HTML 询问 | 材料分析和主构建 Skills | Skill 场景契约测试 |
| Claude/Codex 双端安装 | `scripts/install-skills.py` | `tests/test_installer.py` |

## 发布仓库说明

- 仓库不发布课程样例 MP4；测试会动态构造只含必要 `moov/mvhd` 元数据的极小 MP4。
- 教师材料、ZIP、端到端生成物和浏览器截图不属于发布包。
- 安装器始终忽略 ZIP。

## 验证边界

- `for_test.docx` 端到端样例的 HTML 已在 headless Chromium 中验证桌面与移动视口、四步门控和 `INTERACTION_COMPLETE` 消息；尚未在真实平台 iframe 中验证。
- 来源覆盖检查能发现未处理信息，不能证明内容在学科上正确。
- 教学要素完整性检查不能证明真实学生获得理解、迁移或学习效果。
- 本次没有使用子代理做 Skill 前向测试，因为项目 AGENTS.md 明确要求在主线程顺序执行。
- 已使用场景夹具检查 Skill 的强制门槛和触发描述；实际教师使用后的对话表现仍应继续收集并迭代。

## `for_test.docx` 端到端结果

- Word 成功提取 481 个内容点，其中 31 个标题、355 个带 table/row/cell 坐标的表格内容点。
- 481/481 个内容点映射到 `course.json` 中真实存在的 Block；没有静默舍弃或虚构来源 ID。
- 生成 7 个 Part、17 个 Piece、26 个 Block，以及两份各含 5 个语义锚点的视频交互设计。
- HTML 静态合同通过；浏览器完成消息包含 4 条结构化 interaction 且全部正确后才提交。
- 独立 Review 返回“缺少必要材料，暂不可上传”。阻塞项是两份最终 MP4、10 个事件时间码和真实教师确认；没有课程 schema、生成视图、HTML、来源覆盖或路径格式错误。
- 全套自动测试：57 项通过；5 个 Skill 均通过官方 `quick_validate.py`。

端到端验证使用的教师材料与生成物保留在发布者本地，不进入 GitHub 仓库。
