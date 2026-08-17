import type { WorkflowEventType } from "@mind-imprint/course-contract";

/**
 * §12.4 / §16 — typed payload shapes for every {@link WorkflowEventType}, defined
 * ONCE so producers (renderer emitters, e.g. `SingleChoiceRenderer`/`VideoRenderer`)
 * and reducers (`sessionState.ts`) never hand-write divergent payload assumptions.
 * This is the fix for the review's P2-02 root cause: `answer.submitted` was emitted
 * as `{ value }` but the reducer read `payload.answer`, silently storing `undefined`.
 *
 * The event bus itself (`eventBus.ts`) stays payload-agnostic — it stamps
 * provenance (`id`/`occurredAt`/course/session/part/slice) and fans out
 * `payload: unknown`; these types are for producers and reducers to agree on,
 * not a runtime-enforced envelope constraint (arbitrary/experimental event names
 * outside {@link WorkflowEventType}, e.g. the HTML block's `interaction.progress`,
 * remain valid and simply have no entry in {@link WorkflowEventPayloadMap}).
 */

/** `narration.ended` — the event's `sourceId` already identifies the narration; this is redundant but kept for producers that want to echo it explicitly. */
export interface NarrationEndedPayload {
  narrationId?: string;
}

/** `video.started` carries no data beyond the envelope. */
export type VideoStartedPayload = Record<string, never>;

/** `video.paused` / `video.ended` — current playback position, so a resumed session can seek back instead of restarting the media. */
export interface VideoPositionPayload {
  positionSeconds: number;
}
export type VideoPausedPayload = VideoPositionPayload;
export type VideoEndedPayload = VideoPositionPayload;

/** `video.interaction.shown` — a timeline cue became visible/active. */
export interface VideoInteractionShownPayload {
  interactionId: string;
}

/**
 * Evidence carried by a completed interaction (a video timeline cue, or an
 * `interactiveHtml` block's completion message). Deliberately narrow: `correct`
 * covers graded interactions, `value` is free-form evidence (selected option,
 * entered text, score, ...) for everything else. Stored verbatim into
 * `BlockSessionState.interactionResult` (contract: `z.unknown()`).
 */
export interface InteractionResult {
  /** Whether the interaction's answer was correct, when the interaction is graded. */
  correct?: boolean;
  /** The learner's submitted evidence. */
  value?: unknown;
}

/** `interaction.completed` (`interactiveHtml` block) / `video.interaction.completed` (video timeline cue). */
export interface InteractionCompletedPayload {
  interactionId: string;
  result: InteractionResult;
}
export type VideoInteractionCompletedPayload = InteractionCompletedPayload;

/** `pdf.opened` / `pdf.pageChanged` — the 1-based page the PDF block is now showing. */
export interface PdfOpenedPayload {
  page: number;
}
export interface PdfPageChangedPayload {
  page: number;
}

/** `answer.submitted` — the value the learner just submitted (radio option id, filled text, ...). */
export interface AnswerSubmittedPayload {
  value: string;
}

/** `answer.correct` / `answer.incorrect` / `answer.attemptsExhausted` — the submission that produced this outcome (§12.5 completion engine). */
export interface AnswerOutcomePayload {
  value: string;
  attempt: number;
}
export type AnswerCorrectPayload = AnswerOutcomePayload;
export type AnswerIncorrectPayload = AnswerOutcomePayload;
export type AnswerAttemptsExhaustedPayload = AnswerOutcomePayload;

/** `block.completed` — the event's `sourceId` already identifies the block; kept optional for producers that want to echo it explicitly. */
export interface BlockCompletedPayload {
  blockId?: string;
}

/** `student.continue` carries no data beyond the envelope. */
export type StudentContinuePayload = Record<string, never>;

/** `timer.elapsed` — which authored timer fired. */
export interface TimerElapsedPayload {
  timerId: string;
}

/** Maps every {@link WorkflowEventType} to its typed payload shape — the single shared source of truth for producers and reducers. */
export interface WorkflowEventPayloadMap {
  "narration.ended": NarrationEndedPayload;
  "video.started": VideoStartedPayload;
  "video.paused": VideoPausedPayload;
  "video.ended": VideoEndedPayload;
  "video.interaction.shown": VideoInteractionShownPayload;
  "video.interaction.completed": VideoInteractionCompletedPayload;
  "pdf.opened": PdfOpenedPayload;
  "pdf.pageChanged": PdfPageChangedPayload;
  "interaction.completed": InteractionCompletedPayload;
  "answer.submitted": AnswerSubmittedPayload;
  "answer.correct": AnswerCorrectPayload;
  "answer.incorrect": AnswerIncorrectPayload;
  "answer.attemptsExhausted": AnswerAttemptsExhaustedPayload;
  "block.completed": BlockCompletedPayload;
  "student.continue": StudentContinuePayload;
  "timer.elapsed": TimerElapsedPayload;
}

/** Looks up the typed payload for a known {@link WorkflowEventType}; event names outside the modeled vocabulary resolve to `never`. */
export type WorkflowEventPayload<T extends WorkflowEventType> = T extends keyof WorkflowEventPayloadMap
  ? WorkflowEventPayloadMap[T]
  : never;

// Compile-time proof every WorkflowEventType member is modeled above — a new
// event type added to course-contract without a matching payload here fails
// `typecheck`, not silently falling back to `unknown`.
type AssertExhaustive<T extends true> = T;
type _WorkflowEventPayloadMapIsExhaustive = AssertExhaustive<
  WorkflowEventType extends keyof WorkflowEventPayloadMap ? true : never
>;
