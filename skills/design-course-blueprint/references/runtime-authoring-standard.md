# Runtime authoring standard

## Authority order

1. The three shared packages pinned at `course-authoring-v1.8.0` decide which JSON is accepted and how it is rendered. This tag includes the inline static `richText` Block, full-slot interactive HTML, `aspectRatio: "fill"`, read-only Slice completion on entry, and `openAs: "modal"` on every Block type.
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

For newly designed courses, the page plan also records a learner-visible `journeyContext`: where this Slice sits in the course, what it inherits from the previous Slice, what the learner is focusing on now, and what it prepares next. This planning field is not part of CourseDefinition 2.0; translate it into the Slice's actual learner-facing Blocks and narration. A hidden ID or an internal plan note does not orient a learner.

Every Slice carries two scales of immediate context: its local connection to the previous page's observation, conclusion or artifact, and its position inside the overall method or learning arc. The learner should quickly see why this page appears now, what method or evidence to use, and where the result leads next. Use the lightest suitable surface; this does not require a separate `richText` Block on every page.

Treat one Slice like one teaching slide. Before compiling it, check four things together:

- **content density**: one dominant teaching idea or action fits without tiny text, excessive scrolling, or a large empty card;
- **visual scene**: the focal content is obvious and the layout expresses the relationship between explanation, evidence, and action;
- **continuity**: the learner can tell how this page follows the previous one and what the result will unlock next;
- **student clarity**: the learner sees both the page-to-page connection and the overall framework; before any exercise, they know the current method step, why the exercise appears now, what evidence to use, and what to produce.

A new course begins with an intentional student-facing introduction before the first required response. Choose the form that best fits the material: a story, case conflict, observation task, demonstration, problem situation, or course overview/map. It must make the learning problem and relevance clear and give enough direction for what follows. A complex multi-step method often benefits from a visible route, but a course map is not mandatory. Teach the methodology as a whole before asking the learner to apply one of its parts. Do not open a Slice with an unexplained question.

The contract accepts `full`, `split-horizontal`, `split-vertical`, and `grid`. Split layouts accept `1:1`, `3:2`, `2:3`, `2:1`, `1:2`, `3:1`, and `1:3`; the first weight is left for a horizontal split and top for a vertical split. The teacher-side authoring policy is intentionally narrower: do not generate `split-vertical` by default, and do not stack multiple inline Blocks in `full`. All split Slots must be non-empty. If every Block would occupy one side, use `full`, redistribute the learning surfaces across both sides, or split the sequence into separate Slices; never reserve a dead column or row. The rule is: split-horizontal defaults to `1:1`. Grid supports two to four cells and is selected for a real comparison or grouping need, not from a rigid rule based only on Block count. Do not author nested layouts, coordinates, arbitrary CSS, or course-provided screen dimensions.

### Media-aware composition

Choose the layout from the learning action and natural media aspect while keeping `1:1` as the strong horizontal default:

- **PDF is portrait.** Render it as a centred portrait page within its Slot, never as a stretched wide shallow band. A text-and-PDF split remains `1:1`; PDF does not justify an asymmetric column by itself. Every PDF header has a **放大阅读** action that opens the browser viewer in a large near-fullscreen modal, so the learner can inspect the original without the author giving the PDF a wider Slot. If the learner uses the external-open action, it must open a new tab and leave the course tab intact.
- **Video is wide.** Use `full` for a focused video. The one normal asymmetric split exception is a dominant large video paired with only a small amount of supporting text; the video may receive the wider side. A video paired with substantial content remains `1:1` or is split into another Slice.
- **Interactive HTML owns the complete Slot.** `aspectRatio` is a design hint (`1:1`, `4:3`, or `fill`), not a renderer clamp. The host gives the iframe all available width and height; the document must use that space fluidly, scroll internally when its content is taller, and keep its main task and completion controls reachable. Use `fill` when the interaction has no preferred shape. Check the full interaction at both 1280×720 and a short 1200×520 frame, including its modal-open state when applicable.
- **Rich text is a structured reading card.** Use it for static methodology, worked-example anatomy, comparison, definition, table, rubric, or synthesis content whose hierarchy would be flattened by Markdown. It fills and scrolls inside a tall Slot, carries its HTML inline, references no course asset, and never completes a Slice. Keep short prose as `text`; keep actions in interactive or assessment Blocks.
- **Image groups express a viewing task.** Use `side-by-side` only for exactly two images that must remain visible together for direct comparison. Use `gallery` for more than two images, or for portrait/tall images that would become too small side by side, unless simultaneous comparison is itself the learning action. The gallery already provides previous/next controls.
- **Text and assessments are reading surfaces.** Do not span them across an ultra-wide screen or compress them into a thin row. Pair explanation and action side by side, with the answerable Block in the right slot. Let the renderer's reading card constrain line length.

All split Slots are vertically centred by the shared renderer. These are authoring decisions; the renderer remains responsible for centring, aspect preservation, letterboxing, and safe overflow when it receives a valid definition.

### Inline versus modal Blocks

Every Block may declare `openAs: "inline" | "modal"`; omission means `inline`. `modalLabel` supplies a concise launcher label when the Block's own title, prompt, or alt text would be unclear. Keep the Slice's primary explanation, focal evidence, and the context needed to understand the task inline. Use `modal` for supporting material that benefits from near-fullscreen space—an original document, detailed figure, replayable video, extended reference card, secondary interaction, or a question that would otherwise squeeze its evidence. A modal must release real space and preserve a clear learning sequence; do not hide the page's only instructions, the evidence the learner must notice before acting, or the Slice's core teaching move behind a launcher.

Questions in modal presentation open automatically when the Workflow first enables them, close after completion, and reopen read-only. Resource modals open only when the learner presses their launcher and stay live when reopened. Presentation does not change events, answer payloads, or completion rules. Author `openAs`; the v1.7 assessment-only `presentation` spelling is accepted only for backward compatibility, while `images.presentation` continues to mean image-item layout.

Keep the reference content required to answer a question in the same Slice whenever the combined page remains readable. Do not make learners flip backward during an answer merely because authoring separated the prompt from its evidence.

For AI-authored single-choice questions, vary correct answer positions across the course and do not default every correct answer to the first option. Preserve teacher-provided questions and answer semantics.

For free-text answers, separate reflection from closed-answer checking. Reflection and conceptual explanation use `reflection + submit-any`; they are not graded by keyword or regex. A graded `fillBlank` is reserved for a genuinely closed short answer, includes reasonable accepted variants and actionable `incorrectFeedback`, and uses `submit-correct-or-exhausted` with at most three attempts. The authoring workflow must provide explanation or continuation after exhaustion. Do not generate `submit-correct` for `fillBlank`, even though the shared contract retains it for compatibility.

## Rich-text requirements

`richText` contains one inline `html` string and an optional accessible `title`. It may use isolated inline CSS and the course variables `--course-ink`, `--course-secondary`, `--course-muted`, `--course-surface`, `--course-border`, `--course-accent`, `--course-accent-weak`, and `--course-radius`.

It must not contain scripts, nested frames/objects/embeds, forms, external stylesheets/base tags, inline event handlers, or `javascript:` URLs. Its `srcdoc` has no base URL: remote URLs, relative assets, and webfonts do not load. Use an `images`, `video`, or `pdf` Block for media. Keep the HTML below 64 KB and split long reading across Slices. Always inspect the rendered card in the offline preview before publication.

Use restrained editorial structure, not decorative noise. A meaningful `richText` card contains at least two clearly styled teaching regions, such as a numbered method sequence, a current-step card, a worked example, a comparison, or a hint/callout. Subtle tone variation may be derived from the course variables. Avoid rainbow dashboards, icon clouds, ornamental badges, and a heading plus an ordinary list stretched across a full screen. If the content has no real internal structure, use `text` instead.

When the introduction uses an overview card, it should make the route, cases, and cumulative result visible. Other introduction forms still need to establish the problem, relevance, and direction. A practice-page method card should show the current step, why it is being used now, what prior observation it uses, and what the learner's answer will make possible next.

## Workflow completeness

The final Workflow must contain complete explicit actions and transitions. Do not store a pattern name in place of Workflow data.

All 16 actions remain available:

`show`, `hide`, `focus`, `clearFocus`, `enable`, `disable`, `playNarration`, `pauseNarration`, `stopNarration`, `playBlock`, `pauseBlock`, `resetBlock`, `startTimer`, `cancelTimer`, `completeSlice`, and `navigate`.

All 16 transition Events remain available:

`narration.ended`, `video.started`, `video.paused`, `video.ended`, `video.interaction.shown`, `video.interaction.completed`, `pdf.opened`, `pdf.pageChanged`, `interaction.completed`, `answer.submitted`, `answer.correct`, `answer.incorrect`, `answer.attemptsExhausted`, `block.completed`, `student.continue`, and `timer.elapsed`.

The pinned PDF renderer cannot emit `pdf.pageChanged`, so the authoring policy is `do-not-generate-transition` until the renderer gains a real producer. Recordable runtime events such as `pdf.downloaded`, `image.selected`, and `interaction.progress` are not automatically legal Workflow transition types.

A valid graph has one real initial Step, no unreachable Steps, no ambiguous matchers, no cross-Slice jump, no completion bypass, and a terminal path from every reachable branch. A terminal `navigate` Step has no outgoing transition.

Progress must never depend on getting an answer right. Do not generate `submit-correct`, and do not make `answer.correct` the only route to completion; gate the ordinary exit on `block.completed` and reserve correctness for optional feedback branches. If several answerable Blocks are enabled together, do not wait for their completion events in one fixed order—reveal them sequentially or use an order-independent completion graph. A pure reading Slice completes on entry through an initial Step whose `enterActions` include `completeSlice`; do not hide its exit behind narration or a timer. Do not gate on passive reference Blocks. For a long video with required cues, preserve a visible continuation path so seeking past a cue cannot permanently trap the learner.

## HTML requirements

The iframe protocol is `mind-course-interaction` version `1.0`. Frame messages are `ready`, `progress`, `completed`, and `error`. A `completed` payload must include at least one of `correct` or `value`; `resultId` is optional resend identity.

HTML with audio declares `capabilities.audio: true`, handles `activate`, `deactivate`, `enable`, `disable`, `pauseMedia`, `resumeMedia`, and `stopMedia`, and reports autoplay rejection with error code `autoplay-blocked`. HTML without declared audio receives no autoplay capability.

The HTML document must fill the frame it receives. Prefer `width: 100%`, `min-height: 100%`, responsive grid/flex sizing, and vertical overflow where needed. Do not centre and transform a fixed 1024×768 stage from `transform-origin: top left`, resize `body` to a scaled footprint, or combine a fixed `aspect-ratio` wrapper with `overflow: hidden`; those patterns make content unreachable when the frame is shorter or wider than the design box. The complete task, feedback, unmet-requirement explanation, and completion control must remain reachable at 1280×720 and 1200×520. When the Block is modal, inspect the launcher in the Slice and the full opened dialog separately.

## Review boundary

Contract validation answers “can the runtime parse and execute this definition?” Browser preview answers “does the actual student renderer fit and behave correctly?” Teacher Review answers “is this the intended lesson?” All three gates are required.
