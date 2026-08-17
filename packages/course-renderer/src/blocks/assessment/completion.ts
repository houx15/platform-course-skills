import type { BlockDefinition } from "@mind-imprint/course-contract";

/**
 * §9.6 / §9.7 — the completion rule declared on an assessment block. Fill-blank
 * and single-choice share the exact same three-rule union, so the engine and
 * both renderers name one shared type derived from the contract.
 */
export type CompletionRule =
  | Extract<BlockDefinition, { type: "fillBlank" }>["completion"]
  | Extract<BlockDefinition, { type: "singleChoice" }>["completion"];

/** The correctness-bearing runtime Events an assessment submission can produce. */
export type SubmissionEvent = "answer.correct" | "answer.incorrect" | "answer.attemptsExhausted";

export interface SubmissionInput {
  /** Whether the graded answer just submitted was correct. */
  correct: boolean;
  /** 1-based index of the attempt just made. */
  attemptNumber: number;
  rule: CompletionRule;
}

export interface SubmissionOutcome {
  /** Correctness/exhaustion Events to emit, in order, after `answer.submitted`. */
  events: SubmissionEvent[];
  /** Whether this submission completes the block (→ `block.completed`). */
  completed: boolean;
  /** Whether the block's input should lock (no further attempts accepted). */
  locked: boolean;
}

/**
 * §12.5 — the single place that resolves whether the FINAL failed attempt emits
 * `answer.incorrect` or `answer.attemptsExhausted`. Both assessment renderers
 * delegate here so fill-blank and single-choice can never diverge.
 *
 * Only for graded / attempt-bearing flows. Survey (single-choice) and reflection
 * (fill-blank) modes have no correctness and bypass this: their renderers emit
 * `answer.submitted` + `block.completed` directly (`submit-any`).
 */
export function evaluateSubmission({ correct, attemptNumber, rule }: SubmissionInput): SubmissionOutcome {
  if (correct) {
    return { events: ["answer.correct"], completed: true, locked: true };
  }

  switch (rule.rule) {
    case "submit-any":
      // Any submission completes; correctness only selects the event.
      return { events: ["answer.incorrect"], completed: true, locked: true };
    case "submit-correct":
      // Unlimited attempts — a wrong answer neither completes nor locks.
      return { events: ["answer.incorrect"], completed: false, locked: false };
    case "submit-correct-or-exhausted":
      if (attemptNumber >= rule.maxAttempts) {
        // Final failed attempt → exhaustion (NOT incorrect); lets the Workflow
        // deliver a full explanation before continuing.
        return { events: ["answer.attemptsExhausted"], completed: true, locked: true };
      }
      return { events: ["answer.incorrect"], completed: false, locked: false };
  }
}
