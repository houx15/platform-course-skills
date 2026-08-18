---
name: apply-preview-feedback
description: Use when a teacher has left course preview annotations and wants the approved content, layout, workflow, media, or interaction changes applied safely.
---

# Apply Preview Feedback

Turn renderer-linked comments into bounded Blueprint revisions. This Skill changes local authoring truth only. It never publishes, uploads, edits the generated runtime definition directly, or treats a runtime defect as a content request.

## Restore and reconcile

1. Run `python _course-toolkit/scripts/course-workflow.py status ROOT --json`, then `python _course-toolkit/scripts/course-workflow.py reconcile ROOT --json` when a session exists.
2. Run:

   ```bash
   python _course-toolkit/scripts/manage-annotations.py reconcile ROOT --json
   ```

3. Work only from annotations attached to a stable semantic target: Course, Part, Slice, Block, image item, or workflow Step ID. Do not guess a replacement target for an orphaned annotation. Ask the teacher to re-anchor it in preview.

## Classify every resolvable annotation

- `mechanical`: a bounded correction to a copy field such as title, label, markdown, caption, alt text, or plain text. It cannot change teaching meaning.
- `semantic`: any change to layout, workflow, navigation, media, timing, answers, feedback, completion, learning purpose, source use, or substantive wording.
- `runtime-bug`: renderer behavior does not match the valid definition. It has no Blueprint mutation and remains a G7 blocker for the student-platform developer.

Do not combine unrelated annotations. Preserve the annotation ID, target ID, current Blueprint/definition/source-map hashes, and current value evidence.

## Prepare the bounded plan

Write `.course-work/annotation-revision-plan.json` with one entry per annotation. Every replacement operation must use a relative JSON pointer and `beforeHash` of the exact current value. Mechanical entries may replace copy fields only. Semantic entries require a context-hashed decision ID. Runtime-bug entries contain no operations.

Run:

```bash
python _course-toolkit/scripts/manage-annotations.py prepare ROOT \
  .course-work/annotation-revision-plan.json \
  --json
```

Preparation verifies target binding, hashes, operation boundaries, and decision context. If anything is stale, rebuild the plan from current evidence rather than bypassing the check.

## Obtain decisions and apply

Present each semantic proposal in teacher language: current behavior, requested behavior, affected Slice/Block/Step, and learning consequence. Apply it only after explicit teacher approval and rationale for that exact decision:

```bash
python _course-toolkit/scripts/course-workflow.py confirm-decision ROOT DECISION_ID \
  --choice approve \
  --rationale "TEACHER_RATIONALE" \
  --json
```

Mechanical corrections do not need semantic approval, but must still appear in the plan and audit trail. Never infer approval from the original annotation when the requested change is semantic.

Apply only the prepared plan:

```bash
python _course-toolkit/scripts/manage-annotations.py apply ROOT \
  .course-work/annotation-revision-plan.json \
  --json
```

The tool updates `.course-work/course-blueprint.json` atomically. Always edit the Blueprint; never edit `course/course.json`.

## Rebuild and verify

Follow the returned commands without skipping:

```bash
python _course-toolkit/scripts/course-workflow.py reconcile ROOT --json
python _course-toolkit/scripts/course-workflow.py complete-gate ROOT G3 --json
python _course-toolkit/scripts/course-workflow.py complete-gate ROOT G4 --json
python _course-toolkit/scripts/compile-course.py ROOT --json
python _course-toolkit/scripts/course-workflow.py complete-gate ROOT G5 --json
python _course-toolkit/scripts/validate-course-v2.py ROOT --json
python _course-toolkit/scripts/course-workflow.py complete-gate ROOT G6 --json
```

An annotation application changes the Blueprint, so reconciliation invalidates G3 and every downstream gate. Reconfirm G3 and G4 from the already approved decision context before compiling; never jump directly from reconciliation to G5.

Then open a new renderer preview through `preview-platform-course`. Applied annotations remain unverified until the teacher reviews the rebuilt definition and a new renderer preview binds them to current G7 evidence. If any runtime-bug remains, do not claim G7 complete.

## Completion boundary

Report which annotations were applied, rejected, orphaned, or routed as runtime bugs; which teacher decisions were used; and that a new preview is required. This Skill never authorizes OSS upload or student-end submission.
