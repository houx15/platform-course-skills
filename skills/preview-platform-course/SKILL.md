---
name: preview-platform-course
description: Use when an Agent or teacher needs to inspect, annotate, or re-check a locally built CourseDefinition 2.0 course in the real student renderer.
---

# Preview Platform Course

Use the bundled student renderer with local assets. Preview never uploads, publishes, generates TTS, or needs `OSS_ADMIN_KEY`.

## Agent visual check before teacher preview

1. Run the current contract and package checks that apply to the course. Fix actual invalid data, missing assets, broken HTML protocol, or incompatible media. Do not block an older renderable course merely because it has no historical page-plan, audit, G5, or G6 record.
2. Start the preview. `inspection mode` is the default:

   ```bash
   python _course-toolkit/scripts/preview-course.py ROOT
   ```

   In a repository checkout, use `python scripts/preview-course.py ROOT`. Use `--student-workflow` only when an exact gated student-flow experience was explicitly requested.
3. Use the inspection toolbar to open every Slice. `上一页` and `下一页` deliberately bypass unfinished questions, video, HTML, and Workflow gates for reviewers only. They do not change the student runtime or record fake student completion.
4. At a desktop viewport, save and actually inspect one screenshot per Slice. Check the teaching result, not a compliance score:

   - no obviously crowded, clipped, tiny, or mostly empty layout;
   - no empty side of a split and no answer surface hidden in blank space;
   - each image, PDF, video, HTML activity, and question belongs to the intended explanation;
   - material mentioned by a prompt is available on the same Slice whenever the learner needs it to answer;
   - controls and core text are visible, media aspect ratio is sensible, and the page has no runtime error.

5. If a screenshot shows an obvious problem, update the Blueprint, compile, validate, and inspect the affected Slice again. Stop when the course is reasonable to show a teacher. Do not create an elaborate visual-proof process or ask the teacher to supervise these repair rounds.

## Teacher preview and annotations

1. Open the reviewed course in `--inspection` mode by default. The teacher receives the same independent `上一页 / 下一页` controls the Agent used, so an unfinished question, video, or HTML activity cannot trap review. Start a separate normal preview only when the teacher explicitly asks to experience the authored student Workflow exactly.
2. Explain that `127.0.0.1` works only on this computer. Other people should review the course after it is published to the student platform; never recommend a ZIP, copied course folder, or another person's local URL.
3. The annotation panel starts collapsed and point-to-annotate mode starts off. The teacher may open it, click a rendered component, and add a stable Block/item/Slice annotation. Existing annotations may be edited, deleted, marked complete, or reopened.
4. An exact teacher annotation is already an instruction. Do not ask the teacher to approve the same change again. Apply feedback through `apply-preview-feedback`, rebuild, run the Agent visual check again, then return an updated preview.
5. Automatic `applied -> verified` promotion after the teacher completes a current review is allowed. Preserve `dismissed/已完成` when the teacher marked an item resolved; never reopen it merely because a new internal check exists.

## Handoff to publication

When the teacher reaches the local completion screen and no annotation is pending, the preview shows `下一步：发布到学生端`. Record the completed review, then proactively ask in the conversation: `现在发布到学生端吗？` The button is a handoff to the Agent, not a direct upload or publication bypass.

- If no 33-course catalog binding exists, ask only which course name this is. Code supplies its fixed slug, category, cards, introduction, and cover.
- If the binding already exists, do not ask again.
- Publication itself remains an explicit external mutation and requires the teacher's final confirmation.

## Completion boundary

Report what the Agent visually checked, any issues it fixed, and the local preview URL. Preview success does not itself publish anything.
