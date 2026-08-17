import { evaluateSubmission, type CompletionRule } from "../../src/blocks/assessment/completion";

const submitAny: CompletionRule = { rule: "submit-any" };
const submitCorrect: CompletionRule = { rule: "submit-correct" };
const orExhausted = (maxAttempts: number): CompletionRule => ({ rule: "submit-correct-or-exhausted", maxAttempts });

describe("evaluateSubmission (completion-rule engine)", () => {
  // §9.6 / §12.5 — the single place that resolves the final-attempt ambiguity.
  const cases: Array<{
    name: string;
    rule: CompletionRule;
    correct: boolean;
    attemptNumber: number;
    events: string[];
    completed: boolean;
    locked: boolean;
  }> = [
    // submit-any → any submission completes + locks; correctness only picks the event.
    { name: "submit-any correct", rule: submitAny, correct: true, attemptNumber: 1, events: ["answer.correct"], completed: true, locked: true },
    { name: "submit-any wrong", rule: submitAny, correct: false, attemptNumber: 1, events: ["answer.incorrect"], completed: true, locked: true },

    // submit-correct → unlimited attempts; only a correct answer completes.
    { name: "submit-correct correct", rule: submitCorrect, correct: true, attemptNumber: 1, events: ["answer.correct"], completed: true, locked: true },
    { name: "submit-correct wrong (attempts left forever)", rule: submitCorrect, correct: false, attemptNumber: 5, events: ["answer.incorrect"], completed: false, locked: false },

    // submit-correct-or-exhausted maxAttempts:2.
    { name: "or-exhausted correct on attempt 1", rule: orExhausted(2), correct: true, attemptNumber: 1, events: ["answer.correct"], completed: true, locked: true },
    { name: "or-exhausted wrong with attempts left", rule: orExhausted(2), correct: false, attemptNumber: 1, events: ["answer.incorrect"], completed: false, locked: false },
    // KEY: wrong on the final attempt → attemptsExhausted, NOT incorrect.
    { name: "or-exhausted wrong on final attempt", rule: orExhausted(2), correct: false, attemptNumber: 2, events: ["answer.attemptsExhausted"], completed: true, locked: true },
    // beyond the ceiling still exhausts (defensive).
    { name: "or-exhausted wrong past ceiling", rule: orExhausted(3), correct: false, attemptNumber: 4, events: ["answer.attemptsExhausted"], completed: true, locked: true },
  ];

  it.each(cases)("$name", ({ rule, correct, attemptNumber, events, completed, locked }) => {
    const outcome = evaluateSubmission({ correct, attemptNumber, rule });
    expect(outcome.events).toEqual(events);
    expect(outcome.completed).toBe(completed);
    expect(outcome.locked).toBe(locked);
  });
});
