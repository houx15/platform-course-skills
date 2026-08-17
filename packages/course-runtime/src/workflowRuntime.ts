import type { SliceWorkflow, WorkflowAction, WorkflowEventType, WorkflowStep } from "@mind-imprint/course-contract";

/** A Workflow step id (§5 ids are lower-case hyphenated strings). */
export type WorkflowStepId = string;

/**
 * An effect is exactly a WorkflowAction. The interpreter never applies effects
 * itself; it returns them in order for the host (renderer) to perform. Keeping
 * effects as data is what makes the interpreter pure and replayable.
 */
export type WorkflowEffect = WorkflowAction;

/** The typed runtime error thrown on an impossible workflow state (§12.3 last rule). */
export class WorkflowRuntimeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowRuntimeError";
  }
}

/** A runtime event fed to {@link WorkflowRuntime.send}. Only standardized fields match transitions (§12.4). */
export interface WorkflowInputEvent {
  type: WorkflowEventType;
  sourceId?: string;
  interactionId?: string;
  timerId?: string;
}

/**
 * §17.14 — a pure, deterministic interpreter over one already-validated
 * SliceWorkflow. Entering a step arms its transition matchers first (structural:
 * `currentStepId` is set, so `send` queries the new step) and then returns that
 * step's `enterActions` as an ordered effect list. Slice 1 guarantees the graph
 * is well-formed and transitions are unambiguous, so first-match is deterministic.
 *
 * No timers, no async, no wall clock: the same ordered event stream always
 * yields the same effect log and final step.
 */
export class WorkflowRuntime {
  private readonly workflow: SliceWorkflow;
  private readonly steps: Map<WorkflowStepId, WorkflowStep>;
  private readonly restoreStepId: WorkflowStepId | undefined;
  private stepId: WorkflowStepId | undefined;
  private started = false;

  constructor(workflow: SliceWorkflow, opts?: { restoreStepId?: WorkflowStepId }) {
    this.workflow = workflow;
    this.restoreStepId = opts?.restoreStepId;
    this.steps = new Map(workflow.steps.map((step) => [step.id, step]));
  }

  /** Enters `restoreStepId ?? initialStepId`, arming its transitions, and returns its enterActions. */
  start(): WorkflowEffect[] {
    if (this.started) throw new WorkflowRuntimeError("WorkflowRuntime.start() called more than once");
    this.started = true;
    return this.enter(this.restoreStepId ?? this.workflow.initialStepId);
  }

  /**
   * Feeds one event. Returns the target step's enterActions if the first
   * matching transition on the current step fires, or `[]` while waiting.
   */
  send(event: WorkflowInputEvent): WorkflowEffect[] {
    if (this.stepId === undefined) {
      throw new WorkflowRuntimeError("WorkflowRuntime.send() called before start()");
    }
    const step = this.currentStep();
    const transition = step.transitions.find((t) => matches(t.on, event));
    if (!transition) return [];
    return this.enter(transition.to);
  }

  get currentStepId(): WorkflowStepId {
    if (this.stepId === undefined) throw new WorkflowRuntimeError("WorkflowRuntime not started");
    return this.stepId;
  }

  /** True when the current step's enterActions complete the slice or navigate away. */
  get isTerminal(): boolean {
    return this.currentStep().enterActions.some((a) => a.type === "completeSlice" || a.type === "navigate");
  }

  private enter(stepId: WorkflowStepId): WorkflowEffect[] {
    const step = this.steps.get(stepId);
    if (!step) throw new WorkflowRuntimeError(`WorkflowRuntime: unknown step '${stepId}'`);
    // Arm transitions first (set current step), then hand back enterActions.
    this.stepId = stepId;
    return step.enterActions;
  }

  private currentStep(): WorkflowStep {
    const step = this.steps.get(this.stepId as WorkflowStepId);
    if (!step) throw new WorkflowRuntimeError(`WorkflowRuntime: unknown step '${String(this.stepId)}'`);
    return step;
  }
}

/** Matcher semantics (§12.4/§12.5): `type` must equal; a declared id field must equal; an omitted field matches any. */
function matches(matcher: { type: WorkflowEventType; sourceId?: string; interactionId?: string; timerId?: string }, event: WorkflowInputEvent): boolean {
  if (matcher.type !== event.type) return false;
  if (matcher.sourceId !== undefined && matcher.sourceId !== event.sourceId) return false;
  if (matcher.interactionId !== undefined && matcher.interactionId !== event.interactionId) return false;
  if (matcher.timerId !== undefined && matcher.timerId !== event.timerId) return false;
  return true;
}

/**
 * Convenience helper proving determinism: `start()`s a fresh runtime and
 * `send()`s each event, concatenating all emitted effects.
 */
export function replay(
  workflow: SliceWorkflow,
  events: WorkflowInputEvent[],
  opts?: { restoreStepId?: WorkflowStepId },
): { finalStepId: WorkflowStepId; effects: WorkflowEffect[] } {
  const rt = new WorkflowRuntime(workflow, opts);
  const effects: WorkflowEffect[] = [...rt.start()];
  for (const event of events) effects.push(...rt.send(event));
  return { finalStepId: rt.currentStepId, effects };
}
