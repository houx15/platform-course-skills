# PDF Content Block Design

日期：2026-08-09

## 1. 目标

平台课程新增一种原生内容形态 `pdf`，用于向学生完整呈现论文原文、研究报告、政策文件等材料。PDF 是学生可翻页查看和下载的原始证据，不是仅供 AI 提取后改写的输入文件。

第一版不追踪学生是否打开、翻到末页或读完 PDF，也不设置阻塞或完成规则。需要学习证据时，由同一 Piece 或后续 Piece 中的 `singleChoice`、`fillBlank`、`interactiveHtml` 等活动采集。

## 2. 方案选择

采用原生 `pdf` Block，不使用 HTML 包装器，也不扩展为通用附件 Block。

原因：

- 平台可以针对 PDF 提供稳定的内嵌阅读和下载行为；
- 课程合同能明确区分完整原始材料与普通链接；
- Review 可以独立检查 PDF 是否存在、可打开且没有被摘要或截图替代；
- 当前需求只涉及 PDF，通用附件会提前引入 Word、Excel 等未确认行为。

## 3. 课程合同

### 3.1 JSON 结构

```json
{
  "id": "ljungqvist-paper",
  "type": "pdf",
  "title": "Ljungqvist 2010 论文原文",
  "source": "assets/pdfs/ljungqvist-2010.pdf"
}
```

字段规则：

- `id`：全课程唯一，使用小写连字符 ID；
- `type`：固定为 `pdf`；
- `title`：非空、面向学生，能说明文档是什么；
- `source`：课程根目录相对路径，必须位于课程目录内；
- 不允许 `blocking`、`completion` 或虚构阅读进度的字段。

### 3.2 文件目录

```text
course/
├── course.json
├── index.md
└── assets/
    └── pdfs/
        └── ljungqvist-2010.pdf
```

Builder 按原始字节复制老师提供的 PDF，不把它转换成图片、HTML 或重新排版的 PDF。文件名可为满足安全路径要求而规范化，但文件内容不得改变。

### 3.3 平台呈现

平台对 `pdf` Block 提供：

- 完整文档内嵌阅读；
- 页间翻阅；
- 下载原文件；
- 不记录或声称学生已经读完。

生成的 `index.md` 使用：

```markdown
[PDF]

- 标题：Ljungqvist 2010 论文原文
- 文件：[查看或下载完整 PDF](assets/pdfs/ljungqvist-2010.pdf)
```

## 4. 材料分析与教师确认

材料分析必须区分：

1. PDF 仅作为课程构建的原材料，需要抽取、理解和重新组织；
2. PDF 需要作为完整证据材料进入学生课程。

当老师的材料出现“论文原文”“原始报告”“完整政策文件”“附件供学生阅读”等意图，或某个学习活动要求回到一手文档，AI 应主动建议 `pdf` Block，并确认具体文件。

同一份 PDF 可以同时作为构建输入和学生完整材料，但这两个用途必须分别记录。无法可靠读取 PDF 时，AI 不得声称已经理解其内容；如果老师仍确认完整呈现，可以保存为 PDF Block，但与内容有关的教学说明仍需可靠证据。

## 5. Storyboard 行为

`pdf` 加入允许的呈现模态。包含 PDF 的 Piece 必须说明：

- 学生看到哪份完整材料；
- 阅读它是为了定位、比较或验证什么；
- 学生需要采取什么动作；
- 学习证据由哪个评价 Block 采集；若仅供查阅，可以明确无提交活动。

示例：

| Part / Piece | 学生看到什么 | 教学重点 | 呈现方式 | 学生行动 |
| --- | --- | --- | --- | --- |
| 图表溯源 / 原始论文 | Ljungqvist 2010 完整论文 | 回到一手来源检查原图 | pdf | 翻阅并定位对应图表 |

如果课程需要完整 PDF 而文件尚未提供：

- storyboard 的 `assetNeeds` 记录所需文件；
- `.course-work/unresolved.json` 新增 `blocking: true` 的开放项；
- 不在 `course.json` 中引用不存在的占位文件；
- Review 不得返回 `可上传`。

## 6. 确定性验证

### 6.1 结构验证

Schema 和 Python validator 接受 `pdf` Block，并要求 `id`、`type`、`title`、`source`。额外字段继续由 schema 的 `additionalProperties: false` 阻止。

### 6.2 路径与文件验证

路径检查把 PDF 视为课程资源并验证：

- 路径不为绝对路径；
- 不包含父目录逃逸；
- 引用文件存在；
- 文件扩展名为 `.pdf`，大小写不敏感；
- 文件开头包含 PDF 版本标识 `%PDF-`；
- 文件尾部可找到 `%%EOF`。

头尾检查用于阻止空文件、普通文本或仅修改扩展名的伪 PDF。它不能证明 PDF 的所有页面都能正确渲染，因此 Review 仍需打开或渲染检查样例和真实交付材料。

### 6.3 Review 语义

每个包含 PDF 的 Part 在 `resourcesFormat` 和整体 `pdf` 检查项中核查：

- PDF 文件存在并通过静态格式检查；
- 标题面向学生且能识别材料；
- Piece 说明为什么要查看这份材料；
- 老师要求全文时，没有被摘要、节选截图或重建文件替代；
- 与 PDF 内容有关的题目和说明能追溯到原材料；
- 缺失、损坏、错引或未经确认替换的 PDF 阻止上传。

整体 Review 的固定检查项增加 `pdf`。课程没有 PDF Block 时，可以以“课程未使用 PDF，storyboard 也没有未满足的 PDF 需求”为证据通过。

## 7. Skills 迭代

### `analyze-course-materials`

- 识别“抽取 PDF”与“完整呈现 PDF”两种用途；
- 发现论文原文等需求时主动提出 PDF Block；
- 无法读取时明确报告，不静默跳过。

### `build-platform-course`

- 允许 storyboard 选择 `pdf` 模态；
- 复制原始文件而不改写；
- 缺失的必要 PDF 进入阻塞 unresolved；
- 不用文字摘要冒充老师要求的全文。

### `review-platform-course`

- 逐个 PDF Block 检查文件、标题、教学用途和全文要求；
- 在整体 Review 中增加 `pdf` 行；
- 明确静态检查不能证明文档内容正确或所有页面在真实平台中可渲染。

现有 HTML 和视频设计 Skills 不改变。

## 8. 样例与测试

### 自动测试

新增测试覆盖：

- 合法 `pdf` Block；
- 缺少标题或来源；
- 不允许的额外字段；
- 缺失文件；
- 父目录或绝对路径；
- 非 `.pdf` 扩展名；
- 伪 PDF 头或缺失 `%%EOF`；
- `index.md` 的标题和查看/下载链接；
- storyboard 模态与实际 PDF Block 一致；
- Part Review 和整体 Review 包含 PDF 检查；
- Skill 场景包含论文原文和完整 PDF 意图。

### 样例

- tracked fixture 增加一份明确标注为结构测试材料的最小合法 PDF，不冒充真实论文；
- valid course fixture 增加一个 PDF Piece 或 PDF Block，并重新生成 `index.md`；
- 本地 `format/example_output` 同步 PDF 结构，但只使用结构测试材料，不下载或伪造 Ljungqvist 2010 论文；
- 使用 PDF 工具渲染并检查样例 PDF 页面；
- 更新 README、课程合同和验证报告。

## 9. 验证边界

工具可以证明课程引用了存在且具有基本 PDF 结构的文件、生成视图一致、路径安全，并记录了 PDF 的教学用途。它不能仅凭文件头尾证明：

- PDF 每页都能在真实平台正确渲染；
- PDF 是权威或完整的出版版本；
- 论文内容和课程解读在学科上正确；
- 学生已经阅读或理解 PDF。

真实上传前仍需要平台内嵌阅读测试；结论关键的论文内容仍需要教师或学科专家确认。
