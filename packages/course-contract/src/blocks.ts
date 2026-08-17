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

// ---- block members ----
export const TextBlock = z.object({ id: blockIdSchema, type: z.literal("text"), content: z.string() }).strict();

export const ImageItem = z
  .object({ id: z.string().min(1), source: relativeAssetPathSchema, alt: z.string().min(1), caption: z.string().optional() })
  .strict();
export const ImagesBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("images"),
    presentation: z.enum(["single", "side-by-side", "gallery"]),
    items: z.array(ImageItem).min(1),
  })
  .strict();

export const PdfBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("pdf"),
    title: z.string().min(1),
    source: relativeAssetPathSchema,
    initialPage: z.number().int().positive().optional(),
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
  })
  .strict();

export const InteractiveHtmlBlock = z
  .object({
    id: blockIdSchema,
    type: z.literal("interactiveHtml"),
    source: relativeAssetPathSchema,
    protocolVersion: z.literal("1.0"),
    aspectRatio: z.enum(["1:1", "4:3"]),
    completion: z.object({ rule: z.literal("interaction-complete") }).strict().optional(),
    // Optional, back-compat: an authored HTML interaction opts INTO audio only
    // by declaring this capability (Slice 7 Task 2 gates `allow="autoplay"`
    // and the media-lifecycle wiring on it). Absent → no audio capability, so
    // existing courses authored before this field existed stay valid as-is.
    capabilities: z.object({ audio: z.boolean().optional() }).strict().optional(),
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
  })
  .strict();

export const BlockDefinition = z.discriminatedUnion("type", [
  TextBlock,
  ImagesBlock,
  PdfBlock,
  VideoBlock,
  InteractiveHtmlBlock,
  FillBlankBlock,
  SingleChoiceBlock,
]);

export type BlockDefinition = z.infer<typeof BlockDefinition>;
export type BlockType = BlockDefinition["type"];
