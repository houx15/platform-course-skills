import { z } from "zod";
import { blockIdSchema, relativeAssetPathSchema } from "./primitives";
import {
  ChoiceOption,
  FillBlankAssessment,
  FillBlankCompletionRule,
  SingleChoiceAssessment,
  SingleChoiceCompletionRule,
  VideoBlock,
} from "./blocks";
import type { ValidationIssue } from "./validate/types";

/**
 * §14 — the Video Interaction Contract. A declarative media timeline, NOT a
 * second general Workflow engine. A `VideoInteractionDocument` hangs cue-point
 * activities on the timeline of ONE owning Video Block; the runtime watches the
 * video's reported time and fires each cue once.
 *
 * The cue activities reuse the shared assessment sub-schemas (`ChoiceOption`,
 * `SingleChoiceAssessment` / `FillBlankAssessment`, `*CompletionRule`) so cue
 * grading is exactly the same engine as standalone assessment blocks — no
 * second implementation.
 *
 * Cross-document rules Zod cannot express on a single object (cue-id uniqueness,
 * strictly-increasing times, in-duration bounds, and blockId/source match vs the
 * owning Video Block) live in {@link validateVideoInteraction}, the referential
 * layer for this document.
 */

const SingleChoiceActivity = z
  .object({
    type: z.literal("singleChoice"),
    options: z.array(ChoiceOption).min(2),
    assessment: SingleChoiceAssessment,
    completion: SingleChoiceCompletionRule,
  })
  .strict();

const FillBlankActivity = z
  .object({
    type: z.literal("fillBlank"),
    assessment: FillBlankAssessment,
    completion: FillBlankCompletionRule,
  })
  .strict();

export const VideoInteractionActivity = z.discriminatedUnion("type", [SingleChoiceActivity, FillBlankActivity]);

export const VideoInteractionCue = z
  .object({
    id: z.string().min(1),
    atSeconds: z.number().nonnegative(),
    pauseVideo: z.boolean(),
    required: z.boolean(),
    prompt: z.string().min(1),
    activity: VideoInteractionActivity,
  })
  .strict();

export const VideoInteractionDocument = z
  .object({
    schemaVersion: z.literal("1.1"),
    video: z
      .object({
        blockId: blockIdSchema,
        source: relativeAssetPathSchema,
        durationSeconds: z.number().positive(),
        cues: z.array(VideoInteractionCue),
      })
      .strict(),
  })
  .strict();

export type VideoInteractionActivity = z.infer<typeof VideoInteractionActivity>;
export type VideoInteractionCue = z.infer<typeof VideoInteractionCue>;
export type VideoInteractionDocument = z.infer<typeof VideoInteractionDocument>;

type VideoBlock = z.infer<typeof VideoBlock>;

/**
 * §14 referential validation for a structurally-valid VideoInteractionDocument
 * against its owning Video Block. Deterministic: same input → same ordered list.
 *
 * Checks: cue ids unique; `atSeconds` strictly increasing; every cue time inside
 * the document's `durationSeconds`; the document's `blockId`/`source` match the
 * owning block. `video` is the resolved owning Video Block (§9.4).
 */
export function validateVideoInteraction(doc: VideoInteractionDocument, video: VideoBlock): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const add = (path: string, message: string) => issues.push({ path, message, layer: "referential" });

  const { blockId, source, durationSeconds, cues } = doc.video;

  if (blockId !== video.id) add("video.blockId", `interaction blockId '${blockId}' does not match owning video block '${video.id}'`);
  if (source !== video.source) add("video.source", `interaction source '${source}' does not match owning video source '${video.source}'`);

  const seen = new Set<string>();
  let previous = -Infinity;
  cues.forEach((cue, i) => {
    if (seen.has(cue.id)) add(`video.cues[${i}]`, `duplicate cue id '${cue.id}'`);
    seen.add(cue.id);

    if (cue.atSeconds <= previous) {
      add(`video.cues[${i}].atSeconds`, `cue times must be strictly increasing (got ${cue.atSeconds} after ${previous})`);
    }
    previous = cue.atSeconds;

    if (cue.atSeconds > durationSeconds) {
      add(`video.cues[${i}].atSeconds`, `cue time ${cue.atSeconds} is beyond the video duration ${durationSeconds}`);
    }
  });

  return issues;
}
