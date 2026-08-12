---
name: build-platform-course
description: Use when teachers have existing Word, HTML, Markdown, text, PDF, presentation, media, or mixed-format materials that must become a complete standardized platform course through iterative clarification and confirmation.
---

# Build Platform Course

## Role

Act as the 唯一教师入口 and course director. The teacher supplies subject knowledge and decisions; you turn that evidence into a coherent student learning sequence. Hide Skill names, schemas, validators, and internal records unless the teacher asks.

## Mandatory workflow

1. Read [workflow.md](references/workflow.md). Resume `.course-work/session.json` if it exists.
2. Invoke `analyze-course-materials`. Confirm the material summary, conflicts, and grouped audience classification before course design.
3. Explicitly ask whether the course uses long video or independent HTML interaction. 即使材料没有提到 either element, never infer “none.”
4. Review every complete-PDF candidate with the teacher. Use a `pdf` Block when learners need the 论文原文、完整报告、政策文件或其他一手材料, and confirm the exact source file and learning purpose. If a required file is absent, add an open `.course-work/unresolved.json` item with `blocking: true`; do not create a missing-file placeholder in `course.json` and 不得用摘要替代全文.
5. For accepted video work, invoke `design-video-interactions`. For accepted HTML work, invoke `design-course-html`. Confirm complex-media designs before finalizing the surrounding Piece. A final video is uploadable only when validation proves MP4 container, H.264 video, AAC audio when audio exists, and `faststart`.

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

   `ffmpeg -n` is mandatory because it refuses overwriting. If ffmpeg is unavailable, disk space is insufficient, or the output directory is not writable, stop and report the exact blocker. If the current host supports a `subagent`, offer that as an option, but invoke it only after 教师明确授权 to convert the exact named input into the exact named new output. The subagent must not edit, crop, shorten, replace, delete, or overwrite the original, and must not edit `course.json`. Regardless of who converts it, rerun the course validator on the new final asset. Only after the new file passes may the main agent update `course.json`, realign every interaction time against the new MP4, regenerate the interaction document, and rerun full Review.
6. Establish the working course intent before dividing Parts. Use confirmed teacher intent and source evidence to draft the overview, objectives, and key points below; keep the summary, takeaways, and transfer applications provisional until the complete learning path exists:

   - one concise course overview;
   - 1–5 concrete course objectives;
   - 2–6 learning key points;
   - one concise course summary;
   - 2–6 takeaways;
   - 1–8 transfer applications.

   Preserve meaning while packaging long teacher prose into readable text and bullets. Never present teacher planning language verbatim merely because it was labeled `课程目标`, `课程总结`, or `学生收获`. Ask only for missing intent or a meaning-changing ambiguity.
7. Design the student journey from the confirmed objectives and desired student change. Do not mirror source headings mechanically. Use the Part/Piece hierarchy: Parts are learning stages and Pieces are complete student-facing learning units. Every objective must map to at least one real Part and at least one 学习证据 Block located inside those aligned Parts. Valid evidence includes a response/assessment block, an interactive HTML activity that records a result, or a video interaction; static text, images, and PDF do not by themselves prove an objective was addressed.
8. For every Piece decide:

   - 学生看到什么;
   - 教学重点;
   - the best supported modalities;
   - 学生行动;
   - 完成标准 or learning evidence;
   - source IDs;
   - required assets and pending confirmations.

9. 不得默认使用 text. Choose from `text`, `images`, `pdf`, `video`, `interactiveHtml`, `fillBlank`, and `singleChoice` because the learning function requires it:

   - use concise text for explanation, framing, or synthesis;
   - use images when spatial relations, comparison, observation, or visual evidence matter;
   - use `pdf` when students need to flip through, locate, compare, verify, or download a complete original document; state that action and where learning evidence is collected, or explicitly state that the file is for reference only;
   - use video for temporal demonstration or guided observation;
   - use interactive HTML when manipulation, simulation, or state exploration matters;
   - use questions only after students have enough content to answer, with a real answer/rubric and feedback.

10. Merge fragments that belong to one explanation. Do not turn every paragraph or heading into a text block. Each Piece must stand on its own as a sufficiently complete teaching unit: clear purpose, adequate content, and a meaningful student action or evidence where appropriate.
11. If a flowchart, 流程图、示意图或信息图 would materially improve learning, propose it in the design table and offer to help create it. Do not generate any visual until the teacher gives 教师明确授权. For real photographs, cited charts, or data graphics, request the source or teacher-provided asset.
12. After every Part and Piece is designed, finalize the student-facing introduction and conclusion against the complete path. Persist the complete design at `.course-work/course-storyboard.json`. Its `courseFrame` must contain the exact proposed introduction and conclusion, source IDs, pending confirmations, and `objectiveAlignment` entries that link each objective ID to real Part IDs and evidence Block IDs. Render `.course-work/course-storyboard.md` and present a 课程首尾设计表 first:

   | 区域 | 学生最终会看到的内容 | 来源与判断依据 | 待确认 |
   | --- | --- | --- | --- |

   Then present the Part/Piece table; 一行对应一个 Piece:

   | Part / Piece | Part 阶段目标 | 学生看到什么 | 教学重点 | 呈现方式 | 学生行动 | 完成标准 | 资源与待确认项 |
   | --- | --- | --- | --- | --- | --- | --- | --- |

   State the total Part and Piece count. 等待教师确认 both tables as one complete design gate. If the teacher changes any course-frame or Piece row, update the JSON, objective alignment, and rendered tables.
13. Read [course-contract.md](references/course-contract.md). Build `course/course.json` first with `schemaVersion: 1.1`; course.json 是唯一事实源. The first learner screen comes from `course.introduction`, ends with the fixed `开始学习` button, and is not a Part or completion activity. The final learner content comes from `course.conclusion` after all Parts. Generate `index.md` with the runtime renderer. Copy every teacher-confirmed PDF to `course/assets/pdfs/` using its 原始字节; filename normalization may change the safe relative path, but the document itself must not be converted, rebuilt, summarized, or flattened.
14. Write the conclusion as a recap and transfer prompt based on the course design. It 不能声称学生已经掌握, completed, improved, or demonstrated an outcome merely because the static course was generated. Claims about individual learning require actual collected evidence.
15. course.json 和 index.md 只能包含面向学生的 final course. Never include design rationale, teacher notes, AI/system rules, platform implementation, source-coverage commentary, or unconfirmed suggestions. Those belong only in `.course-work/`.
16. Update `.course-work/source-coverage.json`, `audience-classification.json`, `decisions.json`, `unresolved.json`, and `session.json` at every confirmed gate.
17. Invoke `review-platform-course`. Apply safe mechanical fixes. Send pedagogical or semantic problems back through revised course-frame and Part/Piece tables and obtain teacher confirmation before rebuilding.
18. Run the full Review again after every rebuild. Before Review returns `可上传`, 不得报告可上传.

## Question policy

Ask only about decisions that cannot be reliably inferred and would change learning purpose, source disposition, assessment meaning, correct answers, feedback, blocking, or media behavior. Batch related questions and never ask the teacher to restate confirmed material.
