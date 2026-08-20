# Runtime authoring standard

## Authority order

1. `packages/course-contract` pinned at `course-authoring-v1.2.0` decides which JSON is accepted.
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

The contract accepts `full`, `split-horizontal`, `split-vertical`, and `grid`. Split layouts accept `1:1`, `3:2`, `2:3`, `2:1`, `1:2`, `3:1`, and `1:3`; the first weight is left for a horizontal split and top for a vertical split. The teacher-side authoring policy is intentionally narrower: do not generate `split-vertical` by default, and do not stack multiple Blocks in `full`. The rule is: split-horizontal defaults to `1:1`. Grid supports two to four cells and is selected for a real comparison or grouping need, not from a rigid rule based only on Block count. Do not author nested layouts, coordinates, arbitrary CSS, or course-provided screen dimensions.

### Media-aware composition

Choose the layout from the learning action and natural media aspect while keeping `1:1` as the strong horizontal default:

- **PDF is portrait.** Render it as a centred portrait page within its Slot, never as a stretched wide shallow band. A text-and-PDF split remains `1:1`; PDF does not justify an asymmetric column by itself.
- **Video is wide.** Use `full` for a focused video. The one normal asymmetric split exception is a dominant large video paired with only a small amount of supporting text; the video may receive the wider side. A video paired with substantial content remains `1:1` or is split into another Slice.
- **Interactive HTML preserves its authored aspect.** Keep the declared `1:1` or horizontal `4:3` ratio, scale and centre it, and never stretch it to fill an incompatible Slot. If it cannot fit clearly, change the layout or split the Slice.
- **Text and assessments are reading surfaces.** Do not span them across an ultra-wide screen or compress them into a thin row. Pair explanation and action side by side, with the answerable Block in the right slot. Let the renderer's reading card constrain line length.

All split Slots are vertically centred by the shared renderer. These are authoring decisions; the renderer remains responsible for centring, aspect preservation, letterboxing, and safe overflow when it receives a valid definition.

Keep the reference content required to answer a question in the same Slice whenever the combined page remains readable. Do not make learners flip backward during an answer merely because authoring separated the prompt from its evidence.

For AI-authored single-choice questions, vary correct answer positions across the course and do not default every correct answer to the first option. Preserve teacher-provided questions and answer semantics.

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
