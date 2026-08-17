import { useRef, useState } from "react";
import type { BlockRenderer, SingleChoiceBlock } from "../types";
import { evaluateSubmission } from "./completion";

/**
 * §9.7 / §17.12 — the single-choice assessment renderer. Owns selection state,
 * submission, deterministic graded evaluation, attempt counting, configured
 * feedback, and survey capture. It reports outcomes ONLY as runtime Events
 * (`answer.submitted` → correctness/exhaustion → `block.completed`); the
 * WorkflowRuntime owns branching and remediation.
 *
 * The final failed attempt of `submit-correct-or-exhausted` emits
 * `answer.attemptsExhausted` (not `answer.incorrect`) — decided by the shared
 * completion engine (§12.5). Survey mode bypasses grading: it captures the
 * selection and completes on `submit-any`.
 */
export const SingleChoiceRenderer: BlockRenderer<SingleChoiceBlock> = ({ block, state, visible, enabled, emit }) => {
  const [selected, setSelected] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  // Correctness of the shown feedback, surfaced as `data-correct` so the
  // stylesheet can tint it success/danger; null = ungraded (survey), neutral.
  const [feedbackCorrect, setFeedbackCorrect] = useState<boolean | null>(null);

  // Local 1-based attempt counter, seeded ONCE from persisted state so a
  // remediated (disable → re-enable) question continues its attempt count.
  const attemptsRef = useRef<number | null>(null);
  if (attemptsRef.current === null) attemptsRef.current = state.attempts ?? 0;

  const controlDisabled = !enabled || locked;

  const submit = () => {
    if (controlDisabled || selected === null) return;
    const value = selected;
    emit(block.id, "answer.submitted", { value });

    if (block.assessment.mode === "survey") {
      // No correctness — capture and complete (submit-any).
      setLocked(true);
      setFeedback("已记录你的选择。");
      setFeedbackCorrect(null);
      emit(block.id, "block.completed", {});
      return;
    }

    const attemptNumber = attemptsRef.current! + 1;
    attemptsRef.current = attemptNumber;

    const correct = value === block.assessment.correctOptionId;
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
      data-block-type="singleChoice"
      hidden={!visible}
      aria-hidden={!visible}
      className="course-block course-block--single-choice"
    >
      <p className="course-single-choice__prompt" data-single-choice-prompt>
        {block.prompt}
      </p>
      <div className="course-single-choice__options" role="radiogroup" aria-label={block.prompt}>
        {block.options.map((option) => (
          <label key={option.id} className="course-single-choice__option">
            <input
              type="radio"
              name={block.id}
              value={option.id}
              checked={selected === option.id}
              disabled={controlDisabled}
              aria-label={option.label}
              onChange={() => setSelected(option.id)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
      <button
        type="button"
        className="course-single-choice__submit"
        disabled={controlDisabled || selected === null}
        onClick={submit}
      >
        提交
      </button>
      {feedback ? (
        <p
          className="course-single-choice__feedback"
          role="status"
          data-single-choice-feedback
          data-correct={feedbackCorrect === null ? undefined : feedbackCorrect ? "true" : "false"}
        >
          {feedback}
        </p>
      ) : null}
    </div>
  );
};
