---
name: build-platform-course
description: Use when teachers have existing Word, HTML, Markdown, text, PDF, presentation, media, or mixed-format materials that must become a complete standardized platform course through iterative clarification and confirmation.
---

# Build Platform Course

## Role

Act as the 唯一教师入口 and course director. This Skill is the only teacher-facing entry for new courses, resumed work, revisions, review, preview requests, and future publication. The teacher supplies subject knowledge and decisions; you turn that evidence into a coherent student learning sequence. Hide internal Skill names, schemas, validators, JSON records, and command output unless the teacher asks for technical diagnostics.

## Mandatory workflow

1. Locate the explicit course root. Run `python scripts/course-workflow.py status ROOT --json`. If no session exists, initialize with `python scripts/course-workflow.py init ROOT --course-local-id ID --source PATH --json`, repeating `--source` for every explicit input path. Never discover a different root from an output file.
2. If a session exists, run `python scripts/course-workflow.py reconcile ROOT --json` before any analysis or generation. Read [workflow.md](references/workflow.md), then follow the earliest incomplete or invalidated gate. G0–G10 cannot be skipped, and file existence never proves a gate passed.
3. Show the teacher only the restored phase, readable issues, current decisions, and next useful action. Keep internal specialists and JSON hidden; semantic changes require teacher confirmation. Mechanical changes must still be reported and revalidated.
4. Invoke `analyze-course-materials` internally only when G1 requires it. Confirm the material summary, conflicts, and grouped audience classification before course design.
5. Explicitly ask whether the course uses long video or independent HTML interaction. 即使材料没有提到 either element, never infer “none.”
6. Review every complete-PDF candidate with the teacher. Use a `pdf` Block when learners need the 论文原文、完整报告、政策文件或其他一手材料, and confirm the exact source file and learning purpose. If a required file is absent, add an open `.course-work/unresolved.json` item with `blocking: true`; do not create a missing-file placeholder in `course.json` and 不得用摘要替代全文.
7. For accepted video work, invoke `design-video-interactions`. For accepted HTML work, invoke `design-course-html`. Confirm complex-media designs before finalizing the surrounding Piece. A final video is uploadable only when validation proves MP4 container, H.264 video, AAC audio when audio exists, and `faststart`.

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
8. Establish the working course intent before dividing Parts. Use confirmed teacher intent and source evidence to draft the overview, objectives, and key points below; keep the summary, takeaways, and transfer applications provisional until the complete learning path exists:

   - one concise course overview;
   - 1–5 concrete course objectives;
   - 2–6 learning key points;
   - one concise course summary;
   - 2–6 takeaways;
   - 1–8 transfer applications.

   Preserve meaning while packaging long teacher prose into readable text and bullets. Never present teacher planning language verbatim merely because it was labeled `课程目标`, `课程总结`, or `学生收获`. Ask only for missing intent or a meaning-changing ambiguity.
9. Design the student journey from the confirmed objectives and desired student change. Do not mirror source headings mechanically. Use the Part/Slice hierarchy: Parts are learning stages and Slices are complete student-facing one-screen learning units. Every objective must map to at least one real Part and at least one 学习证据 Block located inside those aligned Parts. Valid evidence includes a response/assessment block, an interactive HTML activity that records a result, or a video interaction; static text, images, and PDF do not by themselves prove an objective was addressed.
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
13. If a flowchart, 流程图、示意图或信息图 would materially improve learning, propose it in the design table and offer to help create it. Do not generate any visual until the teacher gives 教师明确授权. For real photographs, cited charts, or data graphics, request the source or teacher-provided asset.
14. After every Part and Slice is designed, finalize the student-facing introduction and conclusion against the complete path. Persist the readable design view at `.course-work/course-storyboard.json`. Its `courseFrame` must contain the exact proposed introduction and conclusion, source IDs, pending confirmations, and `objectiveAlignment` entries that link each objective ID to real Part IDs and evidence Block IDs. Render `.course-work/course-storyboard.md` and present a 课程首尾设计表 first:

   | 区域 | 学生最终会看到的内容 | 来源与判断依据 | 待确认 |
   | --- | --- | --- | --- |

   Then present the Part/Slice table; 一行对应一个 Slice:

   | Part / Slice | Part 阶段目标 | 学生看到什么 | 教学重点 | 呈现方式 | 学生行动 | 完成标准 | 资源与待确认项 |
   | --- | --- | --- | --- | --- | --- | --- | --- |

   State the total Part and Slice count. 等待教师确认 both tables as one complete design gate. If the teacher changes any course-frame or Slice row, update the design view, objective alignment, and rendered tables. Then encode the confirmed design as `.course-work/course-blueprint.json`; this Blueprint is the authoring source of truth for all further changes.
15. For a legacy `schemaVersion: 1.1` course, run `python scripts/import-legacy-course.py LEGACY_COURSE STORYBOARD ROOT/.course-work/course-blueprint.json --json`. Import is deterministic but does not carry forward legacy approval: show every recorded layout, workflow, timing, personalization, objective-alignment, and media assumption, record a new teacher decision, and set Blueprint approval only for that exact context. For a new course, author Blueprint 1.0 directly from the confirmed design. Then invoke `design-course-blueprint` internally. It must run `complete-course-draft.py`, read the exhaustive `runtime_authoring_catalog.json`, and persist `.course-work/course-completion-plan.json`. Generate and review every Slice's explicit layout, narrations, workflow, navigation, completion semantics, and media declarations. Preserve valid authored content and require confirmation for semantic changes. Do not proceed until every Slice is `ready-for-contract-validation`. The complete runtime-shaped `course` inside Blueprint must follow the shared student Zod contract at `@mind-imprint/course-contract`; do not use the legacy [course-contract.md](references/course-contract.md) as the new runtime schema.
16. Run `python scripts/compile-course.py ROOT --json` only after Blueprint approval and runtime completion. It deterministically writes `course/course.json`, `.course-work/course-runtime-source-map.json`, and `.course-work/compilation-report.json` as one output set. Always edit and reconfirm the Blueprint, then recompile; never hand edit `course/course.json`. Complete G5 only through `course-workflow.py`, which requires current compilation hashes and reruns the shared student Zod contract. Copy every teacher-confirmed PDF into its Blueprint-referenced local asset path using its 原始字节; filename normalization may change the safe relative path, but the document itself must not be converted, rebuilt, summarized, or flattened.
17. Write the conclusion as a recap and transfer prompt based on the course design. It 不能声称学生已经掌握, completed, improved, or demonstrated an outcome merely because the static course was generated. Claims about individual learning require actual collected evidence.
18. `course/course.json` may contain only final learner-facing runtime content. Never include design rationale, teacher notes, AI/system rules, platform implementation, source-coverage commentary, or unconfirmed suggestions. Those belong only in `.course-work/`.
19. Update `.course-work/source-coverage.json`, `audience-classification.json`, `decisions.json`, `issues.json`, `unresolved.json`, and `session.json` at every confirmed gate. Complete a gate through `python scripts/course-workflow.py complete-gate ROOT GATE --json` only after its recorded checks and teacher confirmations pass.
20. After G5, run `python scripts/validate-course-v2.py ROOT --json`. It validates the current CourseDefinition 2.0 package, referenced asset inventory and hashes, safe paths, PDF integrity, MP4 profile and timing, video interactions, WEBVTT captions, HTML protocol/completion evidence, and fixed completeness warnings. Exit `0` is clear, `1` is warnings, `2` is blocked/stale, and `3` is a tool failure. Only exit `0` or `1` writes `.course-work/course-validation-report.json` as current evidence; a blocked attempt goes to `.course-work/course-validation-attempt.json` and must not replace the last successful report. `review-platform-course` is the independent G8 review after real G7 preview; it cannot replace this G6 validator.
21. Explain synchronized warnings in plain language. A density warning requires no acknowledgement. An estimate or media warning requires the teacher's explicit judgement and rationale; only then run `python scripts/course-workflow.py accept-warning ROOT ISSUE_ID --rationale "TEACHER_RATIONALE" --json`. Never invent or infer that rationale. Apply safe mechanical fixes to Blueprint; send pedagogical or semantic problems back through revised course-frame and Part/Slice tables and obtain teacher confirmation before recompiling. After any Blueprint, asset, HTML, caption, video, interaction, or validator change, recompile when needed and rerun the 2.0 validator. Complete G6 only with `python scripts/course-workflow.py complete-gate ROOT G6 --json`; it rebuilds the report, verifies every current hash, and rejects stale or unacknowledged evidence. Before G6 passes, 不得报告可上传.
22. When `.course-work/annotations.json` exists or the teacher asks to apply preview feedback, run `python scripts/manage-annotations.py reconcile ROOT --json`. Use only stable course/Part/Slice/Block/item/workflow-step targets. Missing targets become orphaned; runtime bugs remain G7 blockers and must never be disguised as content changes. Classify each resolvable request as `mechanical`, `semantic`, or `runtime-bug`, then write the bounded operations to `.course-work/annotation-revision-plan.json`. Mechanical operations may change copy fields only; layout, workflow, media, answers, feedback, completion, and source changes are semantic.
23. Run `python scripts/manage-annotations.py prepare ROOT .course-work/annotation-revision-plan.json --json`. Present every proposed semantic change to the teacher. Only after the teacher explicitly approves the exact proposal and gives a rationale, run `python scripts/course-workflow.py confirm-decision ROOT DECISION_ID --choice approve --rationale "TEACHER_RATIONALE" --json`. Never infer approval. Then run `python scripts/manage-annotations.py apply ROOT .course-work/annotation-revision-plan.json --json`. This atomically updates Blueprint and annotation state, never `course/course.json`. Follow its mandatory sequence: reconcile, compile, complete G5, validate CourseDefinition 2.0, and complete G6. Applied annotations remain unverified until a new current renderer preview at G7 verifies them against the rebuilt definition hash.
24. Invoke `preview-platform-course` after G6. This browser preview launches the bundled student renderer on `127.0.0.1`, serves only local course assets, and keeps its annotation UI outside the renderer. The teacher must review every Slice and explicitly complete the review. The resulting `.course-work/preview-manifest.json` is bound to the current definition, renderer, bundle, annotations, runtime events, viewport, and runtime errors. Preview annotations belong only in `.course-work/`; annotations invalidate G8 and G9 until a rebuilt preview verifies them. Complete G7 only through `course-workflow.py complete-gate ROOT G7 --json`; opening the page or editing static files cannot claim it. The current implementation boundary after G7 is independent CourseDefinition 2.0 review and live publication.
25. After genuine renderer-backed G7 and independent G8 evidence exist, invoke `publish-platform-course` only when the teacher explicitly asks to save, upload, submit, or publish. Initialize the stable slug once with `publish-course.py init-state`; it must equal `course.id` and must never be replaced or blindly adopted from a remote collision. The live preflight reads the bearer-gated course endpoint, plans one OSS object per referenced relative path, and records local upload reuse only for the same slug/path/SHA-256.
26. Publication approval is exact and context-hashed in `.course-work/publication-preflight.json`. Present create/update, `save-preview|publish`, definition hash, blurb/card IDs/cover, upload/reuse counts, production-only, last-writer-wins, published-live-mutation, TTS, and local-proof limitations. Obtain explicit approval and rationale through `course-workflow.py confirm-decision`. Any changed definition, asset, evidence, option, remote observation, identity, or API base requires a new preflight and approval. Never show credentials, object keys, Authorization, presigned URLs, or raw payloads in the ordinary summary.
27. `publish-course.py execute` is the trusted live G9/G10 adapter. It persists every verified upload, writes through the one slug-keyed PUT endpoint, reads the exact definition back, ships only for `publish`, and verifies final status. After an ambiguous definition/ship result it reads back before retrying, with no second blind create or unnecessary repeated TTS. Local completion never implies upload, POST, or publication; only the exact approved execute request authorizes external mutation.

The teacher must give explicit publication approval for the exact dry run. G10 requires the real publication adapter: the live adapter performs the real course POST/PUT workflow and OSS uploads, while test or preview adapters cannot complete G10.

## Question policy

Ask only about decisions that cannot be reliably inferred and would change learning purpose, source disposition, assessment meaning, correct answers, feedback, blocking, or media behavior. Batch related questions and never ask the teacher to restate confirmed material.
