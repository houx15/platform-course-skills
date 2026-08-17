import type { BlockSessionState, CourseSession } from "@mind-imprint/course-contract";

// sessionEvidence.ts — P2-05: derives the Closing generator's
// `sessionEvidence` from the actual, validated CourseSession the student just
// played through — never fabricated, never host-supplied. Only signals the
// course opted into (`allowedSignals`, §20 signal minimization) are
// considered; a signal the course didn't permit never touches the closing
// generator's input, mirroring apiSceneGenerator's own `toEvidence` gate on
// the wire. A signal with no recorded data for this session is simply
// omitted — never backfilled with an empty/zero placeholder.
//
// Deterministic: reads only the session object passed in — no wall clock, no
// ids, no randomness.

/** Walks every recorded block across every slice, keeping only defined picks. */
function collectPerBlock(
  session: CourseSession,
  pick: (block: BlockSessionState) => unknown,
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const [sliceId, sliceState] of Object.entries(session.sliceStates)) {
    for (const [blockId, blockState] of Object.entries(sliceState.blockStates)) {
      const value = pick(blockState);
      if (value === undefined) continue;
      (out[sliceId] ??= {})[blockId] = value;
    }
  }
  return out;
}

/**
 * Derives the closing generator's `sessionEvidence` from the validated
 * session, restricted to `allowedSignals` (the course's own `ClosingSignal`
 * enum: "answers" | "attempts" | "time-on-slice" | "interaction-results").
 */
export function buildClosingSessionEvidence(session: CourseSession, allowedSignals: string[]): Record<string, unknown> {
  const allowed = new Set(allowedSignals);
  const evidence: Record<string, unknown> = {};

  if (allowed.has("answers")) {
    const answers = collectPerBlock(session, (b) => b.answer);
    if (Object.keys(answers).length > 0) evidence.answers = answers;
  }
  if (allowed.has("attempts")) {
    const attempts = collectPerBlock(session, (b) => b.attempts);
    if (Object.keys(attempts).length > 0) evidence.attempts = attempts;
  }
  if (allowed.has("interaction-results")) {
    const results = collectPerBlock(session, (b) => b.interactionResult);
    if (Object.keys(results).length > 0) evidence["interaction-results"] = results;
  }
  if (allowed.has("time-on-slice")) {
    const timeOnSlice: Record<string, number> = {};
    for (const [sliceId, sliceState] of Object.entries(session.sliceStates)) {
      if (sliceState.elapsedSeconds > 0) timeOnSlice[sliceId] = sliceState.elapsedSeconds;
    }
    if (Object.keys(timeOnSlice).length > 0) evidence["time-on-slice"] = timeOnSlice;
  }

  return evidence;
}
