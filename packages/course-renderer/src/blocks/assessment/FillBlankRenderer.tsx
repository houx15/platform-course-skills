import { useRef, useState } from "react";
import type { BlockRenderer, FillBlankBlock } from "../types";
import { evaluateSubmission } from "./completion";

/** Case/whitespace-normalized match of a typed value against accepted answers. */
function isCorrect(value: string, acceptedAnswers: string[], caseSensitive: boolean): boolean {
  const normalize = (s: string) => {
    const trimmed = s.trim();
    return caseSensitive ? trimmed : trimmed.toLowerCase();
  };
  const target = normalize(value);
  return acceptedAnswers.some((a) => normalize(a) === target);
}

/**
 * §9.6 / §17.12 — the fill-blank assessment renderer. Owns input state,
 * submission, deterministic graded evaluation, attempt counting, configured
 * feedback, and reflection capture. It reports outcomes ONLY as runtime Events
 * (`answer.submitted` → correctness/exhaustion → `block.completed`); the
 * WorkflowRuntime owns branching and remediation.
 *
 * The final failed attempt of `submit-correct-or-exhausted` emits
 * `answer.attemptsExhausted` (not `answer.incorrect`) — decided by the shared
 * completion engine (§12.5). Reflection mode bypasses grading: it captures the
 * answer and completes on `submit-any`.
 */
export const FillBlankRenderer: BlockRenderer<FillBlankBlock> = ({ block, state, visible, enabled, emit }) => {
  const [value, setValue] = useState("");
  const [locked, setLocked] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  // Correctness of the shown feedback, surfaced as `data-correct` so the
  // stylesheet can tint it success/danger; null = ungraded (reflection).
  const [feedbackCorrect, setFeedbackCorrect] = useState<boolean | null>(null);

  // Local 1-based attempt counter, seeded ONCE from persisted state so a
  // remediated (disable → re-enable) question continues its attempt count.
  const attemptsRef = useRef<number | null>(null);
  if (attemptsRef.current === null) attemptsRef.current = state.attempts ?? 0;

  const disabled = !enabled || locked;

  const submit = () => {
    if (disabled) return;
    emit(block.id, "answer.submitted", { value });

    if (block.assessment.mode === "reflection") {
      // No runtime grading — capture and complete (submit-any).
      setLocked(true);
      setFeedback("已记录你的思考。");
      setFeedbackCorrect(null);
      emit(block.id, "block.completed", {});
      return;
    }

    const attemptNumber = attemptsRef.current! + 1;
    attemptsRef.current = attemptNumber;

    const correct = isCorrect(value, block.assessment.acceptedAnswers, block.assessment.caseSensitive ?? false);
    const outcome = evaluateSubmission({ correct, attemptNumber, rule: block.completion });
    for (const type of outcome.events) emit(block.id, type, { value, attempt: attemptNumber });
    if (outcome.completed) emit(block.id, "block.completed", {});
    if (outcome.locked) setLocked(true);
    setFeedback(correct ? block.assessment.correctFeedback ?? null : block.assessment.incorrectFeedback ?? null);
    setFeedbackCorrect(correct);
  };

  return (
    <div
      data-block-id={block.id}
      data-block-type="fillBlank"
      hidden={!visible}
      aria-hidden={!visible}
      className="course-block course-block--fill-blank"
    >
      <p className="course-fill-blank__prompt" data-fill-blank-prompt>
        {block.prompt}
      </p>
      <input
        type="text"
        className="course-fill-blank__input"
        aria-label={block.prompt}
        placeholder={block.placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="button" className="course-fill-blank__submit" disabled={disabled} onClick={submit}>
        提交
      </button>
      {feedback ? (
        <p
          className="course-fill-blank__feedback"
          role="status"
          data-fill-blank-feedback
          data-correct={feedbackCorrect === null ? undefined : feedbackCorrect ? "true" : "false"}
        >
          {feedback}
        </p>
      ) : null}
    </div>
  );
};
