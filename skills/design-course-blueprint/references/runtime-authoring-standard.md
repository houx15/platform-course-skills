# Runtime authoring standard

## Authority order

1. `packages/course-contract` pinned at `course-authoring-v1.0.0` decides which JSON is accepted.
2. `packages/course-runtime` and `packages/course-renderer` decide which accepted behavior is actually produced and rendered.
3. `2026-08-15-student-course-runtime-data-and-renderer-design.md` explains product meaning.
4. Golden examples demonstrate coverage; they never limit the available options.

Always use `runtime_authoring_catalog.json` as the exhaustive agent-readable index. Its parity checker prevents the catalog from silently drifting from the pinned packages.

## Slice completeness

Every Slice needs:

- stable `id`, title, objective alignment, and duration;
- one or more complete Blocks;
- one supported desktop layout with each Block in exactly one canonical Slot;
- prepared narration transcript and audio path;
- an explicit deterministic Workflow;
- explicit navigation.

Use `full`, `split-horizontal`, `split-vertical`, or `grid`. Split layouts require `1:1`, `2:1`, or `1:2`. Do not author nested layouts, coordinates, arbitrary CSS, or course-provided screen dimensions.

## Workflow completeness

The final Workflow must contain complete explicit actions and transitions. Do not store a pattern name in place of Workflow data.

All 16 actions remain available:

`show`, `hide`, `focus`, `clearFocus`, `enable`, `disable`, `playNarration`, `pauseNarration`, `stopNarration`, `playBlock`, `pauseBlock`, `resetBlock`, `startTimer`, `cancelTimer`, `completeSlice`, and `navigate`.

All 16 transition Events remain available:

`narration.ended`, `video.started`, `video.paused`, `video.ended`, `video.interaction.shown`, `video.interaction.completed`, `pdf.opened`, `pdf.pageChanged`, `interaction.completed`, `answer.submitted`, `answer.correct`, `answer.incorrect`, `answer.attemptsExhausted`, `block.completed`, `student.continue`, and `timer.elapsed`.

The pinned PDF renderer cannot emit `pdf.pageChanged`, so the authoring policy is `do-not-generate-transition` until the renderer gains a real producer. Recordable runtime events such as `pdf.downloaded`, `image.selected`, and `interaction.progress` are not automatically legal Workflow transition types.

A valid graph has one real initial Step, no unreachable Steps, no ambiguous matchers, no cross-Slice jump, no completion bypass, and a terminal path from every reachable branch. A terminal `navigate` Step has no outgoing transition.

## HTML requirements

The iframe protocol is `mind-course-interaction` version `1.0`. Frame messages are `ready`, `progress`, `completed`, and `error`. A `completed` payload must include at least one of `correct` or `value`; `resultId` is optional resend identity.

HTML with audio declares `capabilities.audio: true`, handles `activate`, `deactivate`, `enable`, `disable`, `pauseMedia`, `resumeMedia`, and `stopMedia`, and reports autoplay rejection with error code `autoplay-blocked`. HTML without declared audio receives no autoplay capability.

## Review boundary

Contract validation answers “can the runtime parse and execute this definition?” Browser preview answers “does the actual student renderer fit and behave correctly?” Teacher Review answers “is this the intended lesson?” All three gates are required.
