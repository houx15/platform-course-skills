import type { NavigationDefinition } from "@mind-imprint/course-contract";

export interface CourseNavProps {
  navigation: NavigationDefinition;
  /** The completion-state authority (`SliceSessionState.status === "completed"`) — NEVER a workflow `navigate` effect. */
  completed: boolean;
  /** Omitted (not merely disabled) before the first Slice — §P1-05 "not available before the first Slice". */
  onPrevious?: () => void;
  /** Advances to the next Slice (or Closing past the last one). Shared by both the manual click and an autoNext trigger. */
  onNext: () => void;
  /** True only while the active workflow step actually has a transition waiting on `student.continue` (§P1-05 producer). */
  showContinue: boolean;
  onContinue: () => void;
  /** Present only once `completed` — the explicit re-run-from-initial path (§revisit). */
  onReplay?: () => void;
}

/**
 * §Slice4 / P1-05 — the course-owned navigation bar. Reads the Slice's own
 * `NavigationDefinition` + its live completion state to decide what's
 * clickable; never infers gating from whether a workflow happened to emit an
 * explicit `navigate` effect.
 */
export function CourseNav({ navigation, completed, onPrevious, onNext, showContinue, onContinue, onReplay }: CourseNavProps) {
  const nextDisabled = navigation.manualNext === "after-completion" && !completed;
  return (
    <div className="course-nav" role="group" aria-label="课程导航">
      <button type="button" className="course-nav__previous" onClick={onPrevious} disabled={!onPrevious}>
        上一步
      </button>
      {showContinue ? (
        <button type="button" className="course-nav__continue" onClick={onContinue}>
          继续
        </button>
      ) : null}
      {completed && onReplay ? (
        <button type="button" className="course-nav__replay" onClick={onReplay}>
          重新开始本节
        </button>
      ) : null}
      <button type="button" className="course-nav__next" onClick={onNext} disabled={nextDisabled}>
        下一步
      </button>
    </div>
  );
}
