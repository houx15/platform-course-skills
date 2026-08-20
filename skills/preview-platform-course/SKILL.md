---
name: preview-platform-course
description: Use when a teacher asks to open, inspect, annotate, re-check, or complete renderer-backed review of a locally built CourseDefinition 2.0 course.
---

# Preview Platform Course

Open the course with the real student renderer and keep all review records local. This Skill owns G7 preview evidence; it does not change course content, upload assets, or publish.

## Preconditions

1. Select the course root and run `python _course-toolkit/scripts/course-workflow.py status ROOT --json` (use `python scripts/course-workflow.py` in the repository).
2. Require current G6 package validation and `course/course.json`. If G6 is stale or blocked, return to `build-platform-course`; do not call the page preview evidence.
3. Never request `OSS_ADMIN_KEY`, student login, TTS, signed asset URLs, or live API access. Preview binds only to `127.0.0.1` and uses local assets.

## Open and review

1. Run:

   ```bash
   python _course-toolkit/scripts/preview-course.py ROOT
   ```

   In a repository checkout, use `python scripts/preview-course.py ROOT`. Keep the foreground process running while the teacher reviews the browser URL.
2. Tell the teacher plainly that this is a local preview: the `127.0.0.1` link can be viewed only on this computer. To let another person review it, the course must first be saved or published to the student platform. Explain that the page mounts the real student renderer with in-memory sessions and fallback opening/closing text. It must match student layout, workflow, video interactions, PDF, iframe completion, navigation, and media behavior; the side panel is separate preview chrome.
3. Ask the teacher to traverse every Slice at a desktop viewport, exercise meaningful branches and interactions, and inspect the runtime diagnostics panel. Merely opening the URL is not teacher completion.
4. The preview sidebar has a separate annotation mode. Keep it off while testing the student interaction. Turn annotation mode on only when adding a note; clicking a rendered Block or image then selects its stable semantic target without triggering the learner interaction. In annotation mode, embedded PDF and HTML iframes temporarily stop receiving pointer events so clicking their visible area selects the enclosing Block; turn the mode off to operate them normally. The teacher can also target the whole Slice. Never encode CSS selectors, pixel coordinates, array indexes, signed URLs, or generated DOM structure as the target.
5. Save each comment in the side panel. Existing comments can be edited, deleted, marked complete, or reopened. Mark complete only after the current preview visibly resolves the issue; deletion is for accidental or duplicate notes, not for hiding unresolved feedback.
6. Keep content/layout/workflow/media/question comments separate from runtime errors. A runtime bug must remain classified as a runtime bug and cannot be hidden by rewriting content.

## Finish or revise

1. The teacher may click “确认我已完整审查” only after reviewing every Slice. The preview endpoint writes `.course-work/preview-manifest.json` bound to the current definition hash, pinned renderer tag and package hashes, preview bundle, viewport, visited Slice IDs, exercised events, annotation hash, runtime errors, and completion time.
2. If any required annotation remains open, any Slice is unvisited, the viewport is not desktop-sized, or runtime errors exist, the preview cannot complete G7. Report the exact blocker.
3. When annotations require changes, stop G7 and return control to `build-platform-course`, which routes them through `apply-preview-feedback`. After recompilation and G6 validation, open a new preview. Do not mark applied annotations verified without a current renderer review.
4. When the teacher has explicitly completed a clean, current review, run:

   ```bash
   python _course-toolkit/scripts/course-workflow.py complete-gate ROOT G7 --json
   ```

   This independently verifies the manifest and hashes. Do not edit the manifest or session by hand.

## Completion boundary

Report G7 complete only when `complete-gate ROOT G7` succeeds. A successful browser launch, contract validation, screenshot, or unbound note is insufficient. G7 permits independent final review next; it never implies OSS upload or student-end submission.
