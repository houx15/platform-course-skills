import { z } from "zod";
import { blockIdSchema, relativeAssetPathSchema } from "./primitives";

// NOTE: cross-field rules that Zod cannot express on a single object belong to
// REFERENTIAL validation (see src/validate/referential.ts), not here:
//   - singleChoice graded `correctOptionId` must reference an existing option;
//   - graded fill-blank is incompatible with completion `submit-any`;
//   - video completion `video-ended-and-interactions-completed` requires an
//     `interaction` reference.
// These schemas only enforce the closed per-object shape (§5 strict).

// ---- shared assessment sub-schemas (reused by video cues, §14) ----
export const ChoiceOption = z.object({ id: z.string().min(1), label: z.string().min(1) }).strict();

export const SingleChoiceAssessment = z.discriminatedUnion("mode", [
  z.object({
    mode: z.literal("graded"),
    correctOptionId: z.string().min(1),
    correctFeedback: z.string().optional(),
    incorrectFeedback: z.string().optional(),
  }).strict(),
  z.object({ mode: z.literal("survey") }).strict(),
]);

export const FillBlankAssessment = z.discriminatedUnion("mode", [
  z.object({
    mode: z.literal("graded"),
    acceptedAnswers: z.array(z.string().min(1)).min(1),
    caseSensitive: z.boolean().optional(),
    correctFeedback: z.string().optional(),
    incorrectFeedback: z.string().optional(),
  }).strict(),
  z.object({ mode: z.literal("reflection"), rubric: z.string().min(1) }).strict(),
]);

const submitAny = z.object({ rule: z.literal("submit-any") }).strict();
const submitCorrect = z.object({ rule: z.literal("submit-correct") }).strict();
const submitCorrectOrExhausted = z
  .object({ rule: z.literal("submit-correct-or-exhausted"), maxAttempts: z.number().int().positive() })
  .strict();

export const SingleChoiceCompletionRule = z.discriminatedUnion("rule", [submitAny, submitCorrect, submitCorrectOrExhausted]);
export const FillBlankCompletionRule = z.discriminatedUnion("rule", [submitAny, submitCorrect, submitCorrectOrExhausted]);

/**
 * §9.8 — where a block is surfaced: in its slot, or behind a button.
 *
 * `inline` (the default, and what every block gets by omitting the field)
 * renders it in the slot alongside its siblings.
 *
 * `modal` renders a compact launcher BUTTON in the slot and puts the block
 * itself in a dialog over the slice. It exists because a slice is one desktop
 * screen: the moment two or three resources share it, a `grid` gives each a
 * quarter of the screen, and a PDF page or a slide-sized figure at quarter size
 * is unreadable. Behind a button each one opens at full size on demand, and the
 * slot spends its height on whatever the slice is actually about.
 *
 * Available on EVERY block type — a PDF source, a video, a figure, a reference
 * card, an interaction, or a question. Two behavioural differences by kind:
 *
 *   - An ASSESSMENT block (`fillBlank` / `singleChoice`) opens by itself the
 *     first time the Workflow enables it (the student is meant to answer now),
 *     closes itself on completion, and comes back read-only if reopened — a
 *     remounted assessment would otherwise have lost its local `locked` flag
 *     and could emit a second `block.completed`.
 *   - Every other block opens only when the student presses the button, and
 *     stays interactive when reopened (replaying a video is not a hazard).
 *
 * It is a PRESENTATION choice only: events, completion rules and recorded
 * payloads are identical either way, so a Workflow gating on the block does not
 * change.
 *
 * NOTE this is deliberately NOT called `presentation`: `images` already carries
 * a `presentation` field meaning its item layout (`single` / `side-by-side` /
 * `gallery`), which is an unrelated axis and must stay usable together with
 * this one.
 */
export const BlockOpenAs = z.enum(["inline", "modal"]);

/**
 * Optional label for the launcher button. Defaults to something derived from
 * the block (a question's `prompt`, a PDF's or card's `title`, a figure's
 * `alt`), so authoring it is only needed when you want the button to read
 * differently from the content's own heading.
 */
export const blockModalLabelSchema = z.string().min(1).max(120);

// ---- block members ----
export const TextBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("text"),
    content: z.string(),
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
  })
  .strict();

/**
 * §9.x — `richText`: a scrollable card of AUTHORED, STATIC HTML+CSS, carried
 * INLINE in the definition. It exists because Markdown (the `text` block) tops
 * out well before real editorial structure — callouts, two-column definition
 * lists, colour-coded comparison tables, a styled pull-quote. Those make a dense
 * explanation legible; `text` cannot express them.
 *
 * It is NOT `interactiveHtml`'s smaller sibling. The two differ on every axis
 * that matters:
 *
 *   | | `richText` | `interactiveHtml` |
 *   |-|-|-|
 *   | transport | inline `html` string | an uploaded OSS asset (`source`) |
 *   | scripts   | none, ever           | yes, sandboxed with `allow-scripts` |
 *   | protocol  | none                 | `postMessage` handshake + completion |
 *   | completes a Slice | never (display-only, like `text`) | yes |
 *
 * Because it can never complete anything and never runs code, it carries no
 * `completion` rule and no capabilities. If you want the student to DO
 * something, that is `interactiveHtml` (or an assessment block).
 *
 * The renderer isolates it in a sandboxed iframe with NO `allow-scripts`, so
 * authored `<style>` cannot leak into the app's own CSS and authored markup
 * cannot execute. The rejections below are therefore defence in depth, not the
 * security boundary — they exist so an authoring mistake fails loudly at
 * validate time instead of silently rendering as inert text in a student's
 * screen.
 */
export const RICH_TEXT_MAX_CHARS = 64 * 1024;

/**
 * Constructs that are either inert-by-sandbox (scripts, handlers) or simply
 * cannot work inside a `srcdoc` document with no base URL (`<link>` to a
 * stylesheet, `<base>`), plus tags that have no place in a reading card.
 * Rejected at authoring time with a message that says what to do instead.
 */
const RICH_TEXT_FORBIDDEN: { pattern: RegExp; what: string; instead: string }[] = [
  { pattern: /<\s*script\b/i, what: "<script>", instead: "richText never executes code — use an interactiveHtml block if the student must interact" },
  { pattern: /<\s*(iframe|object|embed)\b/i, what: "<iframe>/<object>/<embed>", instead: "embed media with a video/pdf/images block instead" },
  { pattern: /<\s*form\b/i, what: "<form>", instead: "collect answers with a fillBlank/singleChoice block instead" },
  { pattern: /<\s*(link|base)\b/i, what: "<link>/<base>", instead: "the card has no base URL — put your CSS in an inline <style> block" },
  { pattern: /<[a-z][^>]*\son[a-z]+\s*=/i, what: "an inline event handler (onclick=…)", instead: "richText never executes code" },
  { pattern: /javascript\s*:/i, what: "a javascript: URL", instead: "richText never executes code" },
];

/** The authored HTML itself, with its size cap and its forbidden constructs. */
export const RichTextHtml = z
  .string()
  .min(1)
  .max(RICH_TEXT_MAX_CHARS, `richText html exceeds ${RICH_TEXT_MAX_CHARS} characters — split it across slices`)
  .superRefine((html, ctx) => {
    for (const { pattern, what, instead } of RICH_TEXT_FORBIDDEN) {
      if (pattern.test(html)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `richText html must not contain ${what} — ${instead}` });
      }
    }
  });

export const RichTextBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("richText"),
    /** A self-contained HTML fragment. An inline `<style>` is expected and encouraged. */
    html: RichTextHtml,
    /** Accessible name for the scrollable region; the renderer supplies a generic one when absent. */
    title: z.string().min(1).optional(),
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
  })
  .strict();

export const ImageItem = z
  .object({ id: z.string().min(1), source: relativeAssetPathSchema, alt: z.string().min(1), caption: z.string().optional() })
  .strict();
export const ImagesBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("images"),
    presentation: z.enum(["single", "side-by-side", "gallery"]),
    items: z.array(ImageItem).min(1),
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
  })
  .strict();

export const PdfBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("pdf"),
    title: z.string().min(1),
    source: relativeAssetPathSchema,
    initialPage: z.number().int().positive().optional(),
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
  })
  .strict();

export const VideoBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("video"),
    source: relativeAssetPathSchema,
    poster: relativeAssetPathSchema.optional(),
    captions: relativeAssetPathSchema.optional(),
    durationSeconds: z.number().positive().optional(),
    interaction: z.object({ source: relativeAssetPathSchema }).strict().optional(),
    completion: z
      .discriminatedUnion("rule", [
        z.object({ rule: z.literal("video-ended") }).strict(),
        z.object({ rule: z.literal("video-ended-and-interactions-completed") }).strict(),
      ])
      .optional(),
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
  })
  .strict();

export const InteractiveHtmlBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("interactiveHtml"),
    source: relativeAssetPathSchema,
    protocolVersion: z.literal("1.0"),
    // An authoring HINT describing the shape the interaction was DESIGNED for,
    // never a host clamp: the renderer gives every interactive-HTML block the
    // full slot and lets the frame scroll its own document, whatever this says
    // (see `.course-block--interactive-html` in course.css). Clamping the frame
    // to the ratio used to cut wide interactions down to a narrow column and
    // put their own 完成 button outside the visible box — with
    // `manualNext: "after-completion"` that trapped the student on the slice.
    // `fill` is the explicit "no preferred shape, just give me the slot" value.
    aspectRatio: z.enum(["1:1", "4:3", "fill"]),
    completion: z.object({ rule: z.literal("interaction-complete") }).strict().optional(),
    // Optional, back-compat: an authored HTML interaction opts INTO audio only
    // by declaring this capability (Slice 7 Task 2 gates `allow="autoplay"`
    // and the media-lifecycle wiring on it). Absent → no audio capability, so
    // existing courses authored before this field existed stay valid as-is.
    capabilities: z.object({ audio: z.boolean().optional() }).strict().optional(),
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
  })
  .strict();

export const FillBlankBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("fillBlank"),
    prompt: z.string().min(1),
    placeholder: z.string().optional(),
    assessment: FillBlankAssessment,
    completion: FillBlankCompletionRule,
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
    /**
     * DEPRECATED alias for `openAs`, accepted so a definition authored against
     * course-authoring-v1.7.0 (which briefly named this field `presentation`
     * on assessment blocks) keeps validating and playing. Author `openAs`.
     * Only assessment blocks ever carried it — `images.presentation` is the
     * unrelated item-layout field and is NOT this.
     */
    presentation: BlockOpenAs.optional(),
  })
  .strict();

export const SingleChoiceBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("singleChoice"),
    prompt: z.string().min(1),
    options: z.array(ChoiceOption).min(2),
    assessment: SingleChoiceAssessment,
    completion: SingleChoiceCompletionRule,
    openAs: BlockOpenAs.optional(),
    modalLabel: blockModalLabelSchema.optional(),
    /**
     * DEPRECATED alias for `openAs`, accepted so a definition authored against
     * course-authoring-v1.7.0 (which briefly named this field `presentation`
     * on assessment blocks) keeps validating and playing. Author `openAs`.
     * Only assessment blocks ever carried it — `images.presentation` is the
     * unrelated item-layout field and is NOT this.
     */
    presentation: BlockOpenAs.optional(),
  })
  .strict();

export const BlockDefinition = z.discriminatedUnion("type", [
  TextBlock,
  RichTextBlock,
  ImagesBlock,
  PdfBlock,
  VideoBlock,
  InteractiveHtmlBlock,
  FillBlankBlock,
  SingleChoiceBlock,
]);

export type BlockDefinition = z.infer<typeof BlockDefinition>;
export type BlockType = BlockDefinition["type"];
