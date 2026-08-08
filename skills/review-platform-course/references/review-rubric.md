# Review rubric

## 1. Source and audience fidelity

- Every extracted source ID appears exactly once in `audience-classification.json` and `source-coverage.json`.
- Student core/evidence reaches real course blocks or has teacher-approved exclusion.
- Teacher design, AI/system rules, references, and proposed exclusions remain outside learner output.
- Every merge retains all source IDs and real destinations.
- Every substantive AI addition is confirmed.
- Conflicting source claims remain unresolved until the teacher decides.

## 2. Part-by-Part pedagogical review

Review each Part independently. A polished file does not compensate for a failed dimension.

### `instructionalGoalStructure` — 教学目标与结构

- The Part has one clear stage goal.
- Pieces form an intelligible learning sequence.
- Each Piece contributes to that goal instead of mirroring source headings.

### `contentCompleteness` — 内容完整性

- Each Piece is a sufficiently complete student teaching unit.
- Explanations, examples, instructions, and conclusions needed for understanding are present.
- Source tables, relationships, and evidence were not flattened or fragmented into meaningless text.

### `studentFacingPresentation` — 学生呈现

- Titles and content directly address student learning.
- No design rationale, teacher notes, AI roles, system rules, backend behavior, coverage commentary, or unconfirmed suggestion appears.
- Text is concise and coherent rather than many tiny blocks or raw document dumps.

### `modalityChoice` — 模态选择

- Every block type serves a learning function.
- Text was not used by default where comparison, observation, temporal process, manipulation, or practice calls for another supported modality.
- Images, `pdf`, video, and HTML are used only with real assets and confirmed designs.
- A PDF Piece tells students what to locate, compare, verify, or consult; it does not present a raw file without a learning purpose.

### `practiceFeedback` — 练习与反馈

- Activities appear after adequate instruction.
- Questions have valid answers or rubrics, useful feedback, and appropriate blocking/completion rules.
- Practice provides evidence related to the Part goal.

### `resourcesFormat` — 资源与格式

- All referenced resources exist, use safe relative paths, and meet their specific contracts.
- Images have meaningful alt text.
- Every PDF has a learner-facing title, safe `.pdf` path, `%PDF-` header, `%%EOF` trailer, and the complete document required by the teacher.
- Video and HTML interaction records match actual files.
- The Part's Piece/block structure matches the confirmed storyboard.

For every dimension record `status: pass|revise` and concrete evidence. The Part conclusion is `pass` only if all six dimensions pass.

## 3. Overall review

The second table and `overallChecks` must include:

- `allPartsPass`
- `sourceClassificationCoverage`
- `resourcesPresent`
- `courseJsonSchema`
- `indexConsistency`
- `images`
- `pdf`
- `video`
- `html`
- `assessments`
- `unresolved`

Every check needs `status: pass|revise` plus concrete evidence. A category that is intentionally unused can pass only with evidence that no block or confirmed design requires it.

## 4. Media contracts

PDF files are copied without changing their bytes. When the teacher requested a 论文原文、报告全文或其他完整文档, a summary, screenshot excerpt, reconstructed file, or unconfirmed replacement fails Review. Static header/trailer checks do not prove every page renders in the real platform or that the file is an authoritative edition; test embedded reading and download before upload.

HTML must be one self-contained file with a confirmed task, standardized completion action, valid `INTERACTION_COMPLETE` 1.0 payload, and no prohibited runtime dependency.

The MP4 itself is never generated or modified. Video JSON is canonical, Markdown is generated, declared duration matches the actual MP4, final times are ordered/unique/in range, and no event remains `needs-timing`.

## 5. Outcome labels

- `可上传`: every Part dimension and overall check passes; deterministic validation has no issue.
- `修改后可上传`: only explicitly listed mechanical repairs remain.
- `缺少必要材料，暂不可上传`: any Part needs revision, evidence/asset/decision is missing, or a contract fails.

Never upgrade a result because the files look polished.
