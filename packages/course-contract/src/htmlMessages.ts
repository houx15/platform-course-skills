import { z } from "zod";

/**
 * §17.11 / §20 — versioned, per-message-type payload schemas for the
 * `interactiveHtml` block's `postMessage` protocol (review finding P1-08).
 *
 * The envelope (`protocol`/`version`/`sessionToken`/`type`) is validated by
 * the renderer's `protocol.ts`; these schemas validate the PAYLOAD once the
 * `type` is known, so a well-formed envelope carrying garbage — or, for
 * `completed`, carrying no learning evidence at all — is still rejected
 * before it can complete a block or land in `interactionResult`.
 *
 * Host-owned fields (event id, occurrence time) are stamped by the host bus
 * when the event is appended to the CourseSession; they are never part of
 * these frame-authored payloads and have no place here.
 *
 * `completed` additionally needs a STABLE result identity so a resent
 * `postMessage` (network jitter, a frame re-dispatching after focus, ...) can
 * be recognized as the same logical completion rather than a fresh one. The
 * frame may supply `resultId` for that purpose; the host never trusts it as
 * the block's `interactionId` (that identity is always the block id itself —
 * mirrors how the video-cue pattern keys `interactionResult`), and idempotent
 * handling of a duplicate `completed` message is the caller's responsibility
 * (the renderer), not this schema's.
 */

/** `ready` — the frame signaling it has finished booting. No required data; a plain object of informational fields, or nothing at all. */
export const HtmlReadyPayload = z.record(z.string(), z.unknown()).optional();
export type HtmlReadyPayload = z.infer<typeof HtmlReadyPayload>;

/** `progress` — a free-form, NON-authoritative progress signal (e.g. "3 of 5 steps done"). Never drives completion by itself. */
export const HtmlProgressPayload = z.record(z.string(), z.unknown()).optional();
export type HtmlProgressPayload = z.infer<typeof HtmlProgressPayload>;

/** `error` — the frame reporting its own internal failure. Diagnostics only; requires a human-readable message. */
export const HtmlErrorPayload = z
  .object({
    message: z.string().min(1),
    code: z.string().optional(),
  })
  .strict();
export type HtmlErrorPayload = z.infer<typeof HtmlErrorPayload>;

/**
 * `completed` — the authored interaction's learning evidence. `correct`
 * covers graded interactions; `value` is free-form evidence (selected
 * option(s), entered text, a score, an answers map, ...) for everything
 * else — deliberately mirrors `course-runtime`'s `InteractionResult` shape so
 * the renderer can forward it verbatim. At least one of `correct`/`value`
 * is required: an empty/contentless payload cannot complete a block.
 */
export const HtmlCompletedPayload = z
  .object({
    /** The frame's own stable id for THIS completion, for resend detection. Never used as the host-side interaction identity. */
    resultId: z.string().min(1).optional(),
    correct: z.boolean().optional(),
    value: z.unknown().optional(),
  })
  .strict()
  .refine((p) => p.correct !== undefined || p.value !== undefined, {
    message: "completed payload must carry at least one learning-evidence field (correct and/or value)",
  });
export type HtmlCompletedPayload = z.infer<typeof HtmlCompletedPayload>;

/** The four message types the frame may send — kept in sync with `protocol.ts`'s `FRAME_MESSAGE_TYPES`. */
export type HtmlMessageType = "ready" | "progress" | "completed" | "error";

/** Maps each {@link HtmlMessageType} to its validated payload type. */
export interface HtmlMessagePayloadMap {
  ready: HtmlReadyPayload;
  progress: HtmlProgressPayload;
  completed: HtmlCompletedPayload;
  error: HtmlErrorPayload;
}

/** The single shared source of truth: one schema per {@link HtmlMessageType}. */
export const HTML_MESSAGE_PAYLOAD_SCHEMAS: { [K in HtmlMessageType]: z.ZodType<HtmlMessagePayloadMap[K]> } = {
  ready: HtmlReadyPayload,
  progress: HtmlProgressPayload,
  completed: HtmlCompletedPayload,
  error: HtmlErrorPayload,
};
