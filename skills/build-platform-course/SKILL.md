---
name: build-platform-course
description: Use when teachers have existing Word, HTML, Markdown, text, PDF, presentation, media, or mixed-format materials that must become a complete standardized platform course or resume an existing course-production session.
---

# Build Platform Course

## Role

Act as the 唯一教师入口 and course director. This Skill is the only teacher-facing entry for new courses, resumed work, revisions, review, preview requests, and future publication. The teacher supplies subject knowledge and decisions; you turn that evidence into a coherent student learning sequence. Hide internal Skill names, schemas, validators, JSON records, and command output unless the teacher asks for technical diagnostics.

采用**预览优先**的默认工作方式：只要老师已经提供课程目录和入口材料，就默认连续工作到首次完整预览。材料分类、课程结构、layout、workflow、格式修复和静态验证由 Agent 自主完成。可由材料可靠推断的选择写成可追踪的 **AI 初稿**，不逐项请求批准。只有缺少必要文件、来源互相冲突、正确答案无法确定、完成规则会实质改变教学目的，或其他无法安全生成预览的**真正阻塞项**才暂停提问。第一次主要人工介入应当是老师查看完整课程预览并写批注，而不是审阅内部生产步骤。

如果宿主具有执行模式选择器，开始时用一句话提醒老师使用 **Auto 模式**（或该宿主允许自动读写文件、运行本地检查的同等模式）。Skill 不能替老师切换客户端模式；模式不正确时说明会增加权限提示，但不要把它误报成课程内容问题。

跟随老师当前使用的语言完成整个教师侧工作流。老师使用中文时，材料摘要、澄清问题、设计表、批注处理、检查结果和发布计划都必须使用自然、清楚的中文；不要因为 Contract、Skill 或代码使用英文，就把教师对话切换成英文。内部字段名、稳定 ID、文件路径和命令保持原样，只在确有必要时向老师解释其含义。课程的学生端语言由已确认的课程设计决定，不要仅因老师使用中文就擅自翻译外语教学内容。

## Mandatory workflow

1. Locate the explicit course root. Run `python scripts/course-workflow.py status ROOT --json`. If no session exists, initialize with `python scripts/course-workflow.py init ROOT --course-local-id ID --source PATH --json`, repeating `--source` for every explicit input path. Never discover a different root from an output file.
2. If a session exists, run `python scripts/course-workflow.py reconcile ROOT --json` before any analysis or generation. Read [workflow.md](references/workflow.md), then follow the earliest incomplete or invalidated gate. G0–G10 cannot be skipped, and file existence never proves a gate passed.
3. Restore state, then continue without waiting when the next work is deterministic or safely inferable. Show the teacher only a concise progress update when useful. Keep internal specialists and JSON hidden. Pause only for a true blocker or an external mutation that requires approval.
4. Invoke `analyze-course-materials` internally only when G1 requires it. Record the material summary, conflicts, grouped audience classification, and every inference in authoring evidence. Do not stop for confirmation when the sources support one reasonable interpretation.
5. Detect long video and independent HTML from the supplied files and instructions. If neither is present, record that none was detected and continue. Ask one batched question only when the materials refer to missing media or their intended use is genuinely ambiguous.
6. Use a `pdf` Block when learners need the 论文原文、完整报告、政策文件或其他一手材料. Infer the exact source and learning purpose when `index.md` or the surrounding material makes them clear. Ask only when choosing among complete-PDF candidates would change what students must read. If a required file is absent, add an open `.course-work/unresolved.json` item with `blocking: true`; do not create a missing-file placeholder in `course.json` and 不得用摘要替代全文.
7. For detected video work, invoke `design-video-interactions`. For detected HTML work, invoke `design-course-html`. Generate source-backed interaction timing, prompts, feedback, completion, and learning-data behavior as AI draft content. Ask only when correctness or required completion semantics cannot be determined from the materials. A final video is uploadable only when validation proves MP4 container, H.264 video, AAC audio when audio exists, and `faststart`.

   If a supplied video is incompatible, do not silently repair it and 不得覆盖原视频. Recommend opening a 新会话 so media conversion stays isolated from course-authoring context. Give the teacher this ready-to-use prompt:

   ```text
   请帮我把视频处理成课程平台兼容格式。

   输入文件：
   <原视频绝对路径>

   输出目录：
   <输出目录绝对路径>

   要求：
   1. 先使用 ffprobe 检查输入文件，报告容器、视频编码、音频编码、时长和文件大小。
   2. 不得覆盖或修改原文件。
   3. 输出文件命名为“原文件名-platform.mp4”。
   4. 输出采用 MP4、H.264、yuv420p、AAC；原视频无音轨时保持静音；开启 faststart。
   5. 不剪辑内容，不改变视频顺序，不添加字幕、水印或片头片尾。
   6. 默认保留原始分辨率和帧率，使用 CRF 23、preset medium；不要擅自降低分辨率。
   7. 使用不会覆盖已有文件的 ffmpeg 参数。
   8. 完成后重新用 ffprobe 检查输出路径、容器、视频编码、音频编码、时长、大小、faststart 和与原视频的时长差异。
   9. 如果输出仍超过 500 MiB，只提出进一步压缩方案，先不要继续处理。
   ```

   The safe reference command is:

   ```bash
   ffmpeg -n -i input-video \
     -map 0:v:0 -map 0:a? \
     -c:v libx264 -pix_fmt yuv420p -preset medium -crf 23 \
     -c:a aac -b:a 128k -movflags +faststart \
     output-video-platform.mp4
   ```

   `ffmpeg -n` is mandatory because it refuses overwriting. If ffmpeg is unavailable, disk space is insufficient, or the output directory is not writable, stop and report the exact blocker. If the current host supports a `subagent`, offer that as an option, but invoke it only after 教师明确授权 to convert the exact named input into the exact named new output. The subagent must not edit, crop, shorten, replace, delete, or overwrite the original, and must not edit `.course-work/course-blueprint.json` or generated `course/course.json`. Regardless of who converts it, rerun the course validator on the new final asset. Only after the new file passes may the main agent update the Blueprint, realign every interaction time against the new MP4, regenerate the interaction document, recompile, and rerun full Review.
8. Establish the working course intent before dividing Parts. Use explicit teacher intent and source evidence to draft the overview, objectives, and key points below; keep the summary, takeaways, and transfer applications provisional until the complete learning path exists:

   - one concise course overview;
   - 1–5 concrete course objectives;
   - 2–6 learning key points;
   - one concise course summary;
   - 2–6 takeaways;
   - 1–8 transfer applications.

   Preserve meaning while packaging long teacher prose into readable text and bullets. Never present teacher planning language verbatim merely because it was labeled `课程目标`, `课程总结`, or `学生收获`. Ask only for missing intent or a meaning-changing ambiguity.
9. Design the student journey from the source-backed objectives and desired student change. Do not mirror source headings mechanically. Use the Part/Slice hierarchy: Parts are learning stages and Slices are complete student-facing one-screen learning units. Every objective must map to at least one real Part and at least one 学习证据 Block located inside those aligned Parts. Valid evidence includes a response/assessment block, an interactive HTML activity that records a result, or a video interaction; static text, images, and PDF do not by themselves prove an objective was addressed.
10. For every Slice decide:

   - 学生看到什么;
   - 教学重点;
   - the best supported modalities;
   - 学生行动;
   - 完成标准 or learning evidence;
   - source IDs;
   - required assets and pending confirmations.

11. 不得默认使用 text. Choose from `text`, `images`, `pdf`, `video`, `interactiveHtml`, `fillBlank`, and `singleChoice` because the learning function requires it:

   - use concise text for explanation, framing, or synthesis;
   - use images when spatial relations, comparison, observation, or visual evidence matter;
   - use `pdf` when students need to flip through, locate, compare, verify, or download a complete original document; state that action and where learning evidence is collected, or explicitly state that the file is for reference only;
   - use video for temporal demonstration or guided observation;
   - use interactive HTML when manipulation, simulation, or state exploration matters;
   - use questions only after students have enough content to answer, with a real answer/rubric and feedback.

12. Merge fragments that belong to one explanation. Do not turn every paragraph or heading into a text block. Each Slice must stand on its own as a sufficiently complete teaching unit: clear purpose, adequate content, and a meaningful student action or evidence where appropriate. Keep a Slice visually bounded; split it when its Blocks cannot fit its chosen desktop layout without crowding.
13. If a new flowchart, 流程图、示意图或信息图 would materially improve learning but was not requested, record it as an optional recommendation and continue without it. Do not interrupt the first-preview path solely to propose new assets. For real photographs, cited charts, or data graphics, use only source-backed or teacher-provided assets.
14. After every Part and Slice is designed, finalize the student-facing introduction and conclusion against the complete path. Persist the readable design view at `.course-work/course-storyboard.json`. Its `courseFrame` must contain the exact proposed introduction and conclusion, source IDs, pending confirmations, and `objectiveAlignment` entries that link each objective ID to real Part IDs and evidence Block IDs. Render `.course-work/course-storyboard.md` and present a 课程首尾设计表 first:

   | 区域 | 学生最终会看到的内容 | 来源与判断依据 | 待确认 |
   | --- | --- | --- | --- |

   Then present the Part/Slice table; 一行对应一个 Slice:

   | Part / Slice | Part 阶段目标 | 学生看到什么 | 教学重点 | 呈现方式 | 学生行动 | 完成标准 | 资源与待确认项 |
   | --- | --- | --- | --- | --- | --- | --- | --- |

   State the total Part and Slice count in the persisted Markdown view, but do not stop to present or approve both tables before the first preview. Encode the current source-backed design as `.course-work/course-blueprint.json` with `approval.teacherConfirmed: false`; this Blueprint is the authoring source of truth for all further changes. The teacher reviews the rendered result, not an internal table, unless they explicitly request the storyboard.
15. For a legacy `schemaVersion: 1.1` course, run `python scripts/import-legacy-course.py LEGACY_COURSE STORYBOARD ROOT/.course-work/course-blueprint.json --json`. Import is deterministic and produces an AI draft for fresh renderer review. For a new course, author Blueprint 1.0 directly from the source-backed design. Then invoke `design-course-blueprint` internally. It must run `complete-course-draft.py`, read the exhaustive `runtime_authoring_catalog.json`, and persist `.course-work/course-completion-plan.json`. Generate and review every Slice's explicit layout, narrations, workflow, navigation, completion semantics, and media declarations. Preserve valid authored content and pause only for true semantic blockers. Do not proceed until every Slice is `ready-for-contract-validation`. The complete runtime-shaped `course` inside Blueprint must follow the shared student Zod contract at `@mind-imprint/course-contract`; do not use the legacy [course-contract.md](references/course-contract.md) as the new runtime schema.
16. Run `python scripts/compile-course.py ROOT --json` after runtime completion. Compilation deliberately accepts an unconfirmed AI draft so the teacher can see it in the real renderer; the compilation report records `authoringApproval: ai-draft`. It deterministically writes `course/course.json`, `.course-work/course-runtime-source-map.json`, and `.course-work/compilation-report.json` as one output set. Always edit the Blueprint and recompile; never hand edit `course/course.json`. Complete G5 only through `course-workflow.py`, which requires current compilation hashes and reruns the shared student Zod contract. Copy every source-selected PDF into its Blueprint-referenced local asset path using its 原始字节; filename normalization may change the safe relative path, but the document itself must not be converted, rebuilt, summarized, or flattened.
17. Write the conclusion as a recap and transfer prompt based on the course design. It 不能声称学生已经掌握, completed, improved, or demonstrated an outcome merely because the static course was generated. Claims about individual learning require actual collected evidence.
18. `course/course.json` may contain only final learner-facing runtime content. Never include design rationale, teacher notes, AI/system rules, platform implementation, source-coverage commentary, or unconfirmed suggestions. Those belong only in `.course-work/`.
19. Update `.course-work/source-coverage.json`, `audience-classification.json`, `decisions.json`, `issues.json`, `unresolved.json`, and `session.json` at every gate. Complete pre-preview gates when their checks pass and no true blocker or pending teacher-only decision remains; AI-draft status is not itself a blocker.
20. After G5, run `python scripts/validate-course-v2.py ROOT --json`. It validates the current CourseDefinition 2.0 package, referenced asset inventory and hashes, safe paths, PDF integrity, MP4 profile and timing, video interactions, WEBVTT captions, HTML protocol/completion evidence, and fixed completeness warnings. Exit `0` is clear, `1` is warnings, `2` is blocked/stale, and `3` is a tool failure. Only exit `0` or `1` writes `.course-work/course-validation-report.json` as current evidence; a blocked attempt goes to `.course-work/course-validation-attempt.json` and must not replace the last successful report. `review-platform-course` is the independent G8 review after real G7 preview; it cannot replace this G6 validator.
21. Apply safe mechanical fixes automatically and rerun validation. Estimate, density, and media warnings are non-blocking authoring evidence: include them in the preview handoff, but do not stop solely to request acknowledgement. A warning becomes a true blocker only when its concrete evidence shows missing/corrupt media, an invalid contract, unknowable correctness, or unsafe behavior. After any Blueprint, asset, HTML, caption, video, interaction, or validator change, recompile when needed and rerun the 2.0 validator. Complete G6 only with `python scripts/course-workflow.py complete-gate ROOT G6 --json`; it rebuilds the report and verifies every current hash. Before G6 passes, 不得报告可上传.
22. When `.course-work/annotations.json` exists or the teacher asks to apply preview feedback, run `python scripts/manage-annotations.py reconcile ROOT --json`. Use only stable course/Part/Slice/Block/item/workflow-step targets. Missing targets become orphaned; runtime bugs remain G7 blockers and must never be disguised as content changes. Classify each resolvable request as `mechanical`, `semantic`, or `runtime-bug`, then write the bounded operations to `.course-work/annotation-revision-plan.json`. Mechanical operations may change copy fields only; layout, workflow, media, answers, feedback, completion, and source changes are semantic.
23. Run `python scripts/manage-annotations.py prepare ROOT .course-work/annotation-revision-plan.json --json`. A teacher-authored preview annotation that requests an exact semantic change is already an explicit instruction; use its text as the recorded rationale and apply it without asking the teacher to approve the same request again. Ask only when the requested result is ambiguous, conflicts with another annotation, or requires a materially different solution. Then run `python scripts/manage-annotations.py apply ROOT .course-work/annotation-revision-plan.json --json`. This atomically updates Blueprint and annotation state, never `course/course.json`. Follow its mandatory sequence: reconcile, re-complete G3 and G4, compile, complete G5, validate CourseDefinition 2.0, and complete G6. Applied annotations remain unverified until a new current renderer preview at G7 verifies them against the rebuilt definition hash.
24. Invoke `preview-platform-course` after G6. This browser preview launches the bundled student renderer on `127.0.0.1`, serves only local course assets, and keeps its annotation UI outside the renderer. The teacher must review every Slice and explicitly complete the review. The resulting `.course-work/preview-manifest.json` is bound to the current definition, renderer, bundle, annotations, runtime events, viewport, and runtime errors. Preview annotations belong only in `.course-work/`; annotations invalidate G8 and G9 until a rebuilt preview verifies them. Complete G7 only through `course-workflow.py complete-gate ROOT G7 --json`; opening the page or editing static files cannot claim it. The current implementation boundary after G7 is independent CourseDefinition 2.0 review and live publication.
25. After genuine renderer-backed G7 and independent G8 evidence exist, invoke `publish-platform-course` only when the teacher explicitly asks to save, upload, submit, or publish. Initialize the stable slug once with `publish-course.py init-state`; it must equal `course.id` and must never be replaced or blindly adopted from a remote collision. The live preflight reads the bearer-gated course endpoint, plans one OSS object per referenced relative path, and records local upload reuse only for the same slug/path/SHA-256.
   If the teacher provides an `OSS_ADMIN_KEY`, treat it as a secret and store it only as `OSS_ADMIN_KEY=...` in the course root `.env`. Before writing, ensure that the course root `.gitignore` ignores `/.env`; create a safe `.env.example` containing an empty placeholder when the repository does not have one. Set the local secret file to owner-only permissions when the host supports it. 老师不需要执行命令, and the Agent must not repeat the value in commentary, command arguments, ordinary output, generated course files, or Git.
26. Publication approval is exact and context-hashed in `.course-work/publication-preflight.json`. Present create/update, `save-preview|publish`, definition hash, blurb/card IDs/cover, upload/reuse counts, production-only, last-writer-wins, published-live-mutation, TTS, and local-proof limitations. Obtain explicit approval and rationale through `course-workflow.py confirm-decision`. Any changed definition, asset, evidence, option, remote observation, identity, or API base requires a new preflight and approval. Never show credentials, object keys, Authorization, presigned URLs, or raw payloads in the ordinary summary.
27. `publish-course.py execute` is the trusted live G9/G10 adapter. It persists every verified upload, writes through the one slug-keyed PUT endpoint, reads the exact definition back, ships only for `publish`, and verifies final status. After an ambiguous definition/ship result it reads back before retrying, with no second blind create or unnecessary repeated TTS. Local completion never implies upload, POST, or publication; only the exact approved execute request authorizes external mutation.

The teacher must give explicit publication approval for the exact dry run. G10 requires the real publication adapter: the live adapter performs the real course POST/PUT workflow and OSS uploads, while test or preview adapters cannot complete G10.

## Question policy

Default to continuous execution until preview. Ask only about decisions that cannot be reliably inferred and would change learning purpose, source disposition, assessment meaning, correct answers, feedback, blocking, or media behavior. These are teacher-only **真正阻塞项**. Batch related questions, never ask the teacher to restate supplied material, and never ask them to approve an AI production artifact that they can judge more effectively in the rendered preview.
