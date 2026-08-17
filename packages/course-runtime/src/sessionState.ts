import type { BlockDefinition, BlockSessionState, SliceDefinition, SliceSessionState } from "@mind-imprint/course-contract";
import type { WorkflowEffect } from "./workflowRuntime";
import { WorkflowRuntimeError } from "./workflowRuntime";
import type {
  AnswerSubmittedPayload,
  InteractionCompletedPayload,
  VideoPositionPayload,
} from "./eventPayloads";

/** Blocks that carry attempts + answer state (§12.1 assessment seeding). */
const ASSESSMENT_TYPES: ReadonlySet<BlockDefinition["type"]> = new Set(["singleChoice", "fillBlank"]);

const isAssessment = (block: BlockDefinition): boolean => ASSESSMENT_TYPES.has(block.type);

/**
 * §12.1 defaults. Builds the initial SliceSessionState for a slice:
 * - no `initialState` → every block visible + enabled;
 * - `visibleBlockIds` present → listed visible, unlisted hidden;
 * - `enabledBlockIds` present → listed enabled, unlisted disabled;
 * - omitting either list preserves that list's default.
 * Every block gets `completed:false`; assessment blocks additionally seed `attempts:0`.
 * Slice starts `status:"not-started"`, `elapsedSeconds:0`.
 */
export function initSliceState(slice: SliceDefinition): SliceSessionState {
  const initial = slice.workflow.initialState;
  const visibleList = initial?.visibleBlockIds;
  const enabledList = initial?.enabledBlockIds;

  const blockStates: Record<string, BlockSessionState> = {};
  for (const block of slice.blocks) {
    const visible = visibleList === undefined ? true : visibleList.includes(block.id);
    const enabled = enabledList === undefined ? true : enabledList.includes(block.id);
    const state: BlockSessionState = { visible, enabled, completed: false };
    if (isAssessment(block)) state.attempts = 0;
    blockStates[block.id] = state;
  }

  return { status: "not-started", elapsedSeconds: 0, blockStates };
}

/** Returns a new SliceSessionState with `blockId`'s block state replaced by `next`. */
function withBlock(state: SliceSessionState, blockId: string, next: BlockSessionState): SliceSessionState {
  return { ...state, blockStates: { ...state.blockStates, [blockId]: next } };
}

function requireBlock(state: SliceSessionState, blockId: string): BlockSessionState {
  const block = state.blockStates[blockId];
  if (!block) throw new WorkflowRuntimeError(`sessionState: effect targets unknown block '${blockId}'`);
  return block;
}

/** Parses an ISO-8601 timestamp to epoch ms, or `undefined` if unparseable. Pure — never reads the wall clock. */
function parseTimestamp(value: string): number | undefined {
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : undefined;
}

/**
 * Deterministic elapsed-seconds computation from two ISO-8601 timestamps taken
 * from the event envelope (bus-stamped `occurredAt`) — never `Date.now()`.
 * Falls back to `0` on unparseable/out-of-order input rather than throwing,
 * since a malformed timestamp shouldn't crash the reducer.
 */
function elapsedSecondsBetween(startedAt: string, occurredAt: string): number {
  const start = parseTimestamp(startedAt);
  const end = parseTimestamp(occurredAt);
  if (start === undefined || end === undefined || end < start) return 0;
  return (end - start) / 1000;
}

/**
 * Stamps slice-level position/time (§16 resume) from a bus-provided timestamp:
 * the first touch moves `status` "not-started" → "in-progress" and records
 * `startedAt`; every touch recomputes `elapsedSeconds` as the delta from
 * `startedAt`. A no-op once the slice is `completed` (frozen by
 * {@link applyEffect}'s `completeSlice` case) or once nothing would change.
 */
function touchSliceTiming(state: SliceSessionState, occurredAt: string): SliceSessionState {
  if (state.status === "completed") return state;
  const startedAt = state.startedAt ?? occurredAt;
  const elapsedSeconds = elapsedSecondsBetween(startedAt, occurredAt);
  const status = state.status === "not-started" ? "in-progress" : state.status;
  if (state.startedAt === startedAt && state.status === status && state.elapsedSeconds === elapsedSeconds) {
    return state;
  }
  return { ...state, status, startedAt, elapsedSeconds };
}

/**
 * Records the slice's current WorkflowRuntime step (§16 resume position). The
 * host calls this after `WorkflowRuntime.start()`/`.send()` advances
 * (`runtime.currentStepId`) — the reducer has no view of workflow steps itself.
 */
export function setCurrentWorkflowStep(state: SliceSessionState, stepId: string): SliceSessionState {
  if (state.currentWorkflowStepId === stepId) return state;
  return { ...state, currentWorkflowStepId: stepId };
}

/**
 * Folds one WorkflowEffect onto persisted block/slice state. Visibility and
 * interactivity effects flip the target block; `resetBlock` clears its progress;
 * `completeSlice` marks the slice completed and (when `occurredAt` is supplied)
 * stamps `completedAt` and freezes `elapsedSeconds` at that instant. Transient
 * effects (focus, narration, timer, media play/pause) carry no persisted state
 * and return `state` unchanged. Never mutates; always returns a new object when
 * something changes.
 *
 * `occurredAt` is optional and, when provided, MUST come from the triggering
 * event's envelope timestamp (never a fresh clock read) — omit it to leave
 * `completedAt`/`elapsedSeconds` untouched (e.g. replay contexts that don't
 * track wall time).
 *
 * Throws {@link WorkflowRuntimeError} on a block-targeting effect whose target
 * does not exist in the slice — an impossible state Slice 1 validation rules out.
 */
export function applyEffect(state: SliceSessionState, effect: WorkflowEffect, occurredAt?: string): SliceSessionState {
  switch (effect.type) {
    case "show":
      return withBlock(state, effect.targetId, { ...requireBlock(state, effect.targetId), visible: true });
    case "hide":
      return withBlock(state, effect.targetId, { ...requireBlock(state, effect.targetId), visible: false });
    case "enable":
      return withBlock(state, effect.targetId, { ...requireBlock(state, effect.targetId), enabled: true });
    case "disable":
      return withBlock(state, effect.targetId, { ...requireBlock(state, effect.targetId), enabled: false });
    case "resetBlock":
      return withBlock(state, effect.targetId, {
        ...requireBlock(state, effect.targetId),
        completed: false,
        attempts: 0,
        answer: undefined,
      });
    case "completeSlice": {
      const elapsedSeconds =
        occurredAt && state.startedAt ? elapsedSecondsBetween(state.startedAt, occurredAt) : state.elapsedSeconds;
      return { ...state, status: "completed", completedAt: occurredAt ?? state.completedAt, elapsedSeconds };
    }
    // Transient / non-persisted effects — no block-state change.
    case "focus":
    case "clearFocus":
    case "playNarration":
    case "pauseNarration":
    case "stopNarration":
    case "playBlock":
    case "pauseBlock":
    case "startTimer":
    case "cancelTimer":
    case "navigate":
      return state;
    default: {
      // Exhaustiveness guard: a new action type must be handled explicitly.
      const _never: never = effect;
      return _never;
    }
  }
}

/**
 * A minimal runtime-event shape the reducer folds; matches CourseRuntimeEvent's
 * relevant fields. `occurredAt` is optional so pure unit tests can omit it
 * (skips slice timing); the host always has it (the bus stamps every event).
 */
export interface SessionStateEvent {
  type: string;
  sourceId: string;
  payload?: unknown;
  occurredAt?: string;
}

const asRecord = (payload: unknown): Record<string, unknown> | undefined =>
  payload !== null && typeof payload === "object" && !Array.isArray(payload) ? (payload as Record<string, unknown>) : undefined;

/**
 * `interaction.completed` / `video.interaction.completed` can fire more than
 * once for the same block (a video's multiple required timeline cues all share
 * the video block's `sourceId`, keyed by `interactionId`). Merging by
 * `interactionId` into a record keeps every cue's evidence instead of the last
 * one clobbering the rest — `BlockSessionState.interactionResult` is `z.unknown()`
 * in the contract, so this shape is this reducer's choice, not a contract change.
 */
function mergeInteractionResult(existing: unknown, interactionId: string, result: unknown): Record<string, unknown> {
  const base = existing !== null && typeof existing === "object" && !Array.isArray(existing) ? (existing as Record<string, unknown>) : {};
  return { ...base, [interactionId]: result };
}

/**
 * Folds one runtime event onto persisted slice + block state (spec-anchored,
 * small map), using the typed payload shapes from `eventPayloads.ts`:
 * - any event with `occurredAt` first stamps slice timing (§16 resume: first
 *   touch → `status:"in-progress"` + `startedAt`; every touch recomputes
 *   `elapsedSeconds`) via {@link touchSliceTiming};
 * - `answer.submitted` → `attempts += 1`, stores the typed `payload.value`
 *   (P2-02 fix — producers emit `{value}`, not `{answer}`);
 * - `answer.correct` / `block.completed` → marks the source block `completed:true`;
 * - `video.paused` / `video.ended` → records `payload.positionSeconds` as `mediaPositionSeconds`;
 * - `interaction.completed` / `video.interaction.completed` → merges the typed
 *   `payload.result` into `interactionResult`, keyed by `payload.interactionId`.
 * Events whose source is not a block in this slice (e.g. `narration.ended`, whose
 * source is a narration id) leave block state untouched but still update slice
 * timing. Never mutates.
 */
export function applyEvent(state: SliceSessionState, event: SessionStateEvent): SliceSessionState {
  const timed = event.occurredAt ? touchSliceTiming(state, event.occurredAt) : state;
  const block = timed.blockStates[event.sourceId];
  if (!block) return timed;

  switch (event.type) {
    case "answer.submitted": {
      const payload = asRecord(event.payload) as Partial<AnswerSubmittedPayload> | undefined;
      const value = typeof payload?.value === "string" ? payload.value : undefined;
      return withBlock(timed, event.sourceId, {
        ...block,
        attempts: (block.attempts ?? 0) + 1,
        answer: value,
      });
    }
    case "answer.correct":
    case "block.completed": {
      return withBlock(timed, event.sourceId, { ...block, completed: true });
    }
    case "video.paused":
    case "video.ended": {
      const payload = asRecord(event.payload) as Partial<VideoPositionPayload> | undefined;
      const position = typeof payload?.positionSeconds === "number" ? payload.positionSeconds : block.mediaPositionSeconds;
      return withBlock(timed, event.sourceId, { ...block, mediaPositionSeconds: position });
    }
    case "interaction.completed":
    case "video.interaction.completed": {
      const payload = asRecord(event.payload) as Partial<InteractionCompletedPayload> | undefined;
      const interactionId = typeof payload?.interactionId === "string" ? payload.interactionId : event.sourceId;
      return withBlock(timed, event.sourceId, {
        ...block,
        interactionResult: mergeInteractionResult(block.interactionResult, interactionId, payload?.result),
      });
    }
    default:
      return timed;
  }
}
