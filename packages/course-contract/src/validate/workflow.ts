import type { SliceDefinition } from "../course";
import type { ValidationIssue } from "./types";

/** Event matcher types that "gate" a cycle (§12.6). */
const GATED_EVENT_TYPES = new Set(["answer.incorrect", "answer.attemptsExhausted", "student.continue", "timer.elapsed"]);

/** Actions that require a video block target (§12.3). */
const VIDEO_ONLY_ACTIONS = new Set(["playBlock", "pauseBlock", "resetBlock"]);
/** Actions whose `targetId` addresses a block. */
const BLOCK_TARGET_ACTIONS = new Set(["show", "hide", "enable", "disable", "playBlock", "pauseBlock", "resetBlock"]);
/** Narration actions whose `narrationId` addresses a declared narration. */
const NARRATION_ACTIONS = new Set(["playNarration", "pauseNarration", "stopNarration"]);

/**
 * Workflow graph validation (§12.6, §12.3, §12.5) for one slice. Operates on a
 * structurally-valid slice. Deterministic.
 */
export function validateSliceWorkflow(slice: SliceDefinition, path: string): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const add = (p: string, message: string) => issues.push({ path: p, message, layer: "workflow" });
  const wfPath = `${path}.workflow`;

  const wf = slice.workflow;
  const steps = wf.steps as any[];

  // reference sets from the slice
  const blockIds = new Set(slice.blocks.map((b) => b.id));
  const videoBlockIds = new Set(slice.blocks.filter((b) => b.type === "video").map((b) => b.id));
  const narrationIds = new Set(slice.narrations.map((n) => n.id));
  const imageItemIds = new Map<string, Set<string>>();
  for (const b of slice.blocks as any[]) {
    if (b.type === "images") imageItemIds.set(b.id, new Set(b.items.map((it: any) => it.id)));
  }

  // step map + duplicate-id detection
  const stepIds = new Set<string>();
  const stepById = new Map<string, any>();
  steps.forEach((step, si) => {
    if (stepIds.has(step.id)) add(`${wfPath}.steps[${si}]`, `duplicate workflow step id '${step.id}'`);
    stepIds.add(step.id);
    if (!stepById.has(step.id)) stepById.set(step.id, step);
  });

  // timers declared by any startTimer action
  const declaredTimerIds = new Set<string>();
  for (const step of steps) {
    for (const a of step.enterActions as any[]) {
      if (a.type === "startTimer") declaredTimerIds.add(a.timerId);
    }
  }

  // initialStepId exists
  if (!stepIds.has(wf.initialStepId)) {
    add(`${wfPath}.initialStepId`, `initial step references unknown step '${wf.initialStepId}'`);
  }

  // per-step: action targets, transition targets, terminal/navigate rule, ambiguity
  steps.forEach((step, si) => {
    const stepPath = `${wfPath}.steps[${si}]`;
    const actions = step.enterActions as any[];

    actions.forEach((a, ai) => {
      const aPath = `${stepPath}.enterActions[${ai}]`;
      if (BLOCK_TARGET_ACTIONS.has(a.type)) {
        if (!blockIds.has(a.targetId)) add(aPath, `action '${a.type}' references unknown block '${a.targetId}'`);
        else if (VIDEO_ONLY_ACTIONS.has(a.type) && !videoBlockIds.has(a.targetId)) {
          add(aPath, `action '${a.type}' target '${a.targetId}' is not a video block`);
        }
      }
      if (NARRATION_ACTIONS.has(a.type)) {
        if (!narrationIds.has(a.narrationId)) add(aPath, `action '${a.type}' references undeclared narration '${a.narrationId}'`);
      }
      if (a.type === "focus") {
        const t = a.target;
        if (!blockIds.has(t.blockId)) add(aPath, `focus references unknown block '${t.blockId}'`);
        else if (t.itemId !== undefined) {
          const items = imageItemIds.get(t.blockId);
          if (!items || !items.has(t.itemId)) add(aPath, `focus references unknown item '${t.itemId}' in block '${t.blockId}'`);
        }
      }
      if (a.type === "cancelTimer") {
        if (!declaredTimerIds.has(a.timerId)) add(aPath, `cancelTimer references timer '${a.timerId}' that is never started`);
      }
    });

    // terminal navigate rule: a step running `navigate` must have no outgoing transitions (§12)
    const hasNavigate = actions.some((a) => a.type === "navigate");
    if (hasNavigate && step.transitions.length > 0) {
      add(stepPath, `step '${step.id}' navigates and must not have outgoing transitions`);
    }

    // transition targets exist
    (step.transitions as any[]).forEach((t, ti) => {
      if (!stepIds.has(t.to)) add(`${stepPath}.transitions[${ti}]`, `transition references unknown step '${t.to}'`);
    });

    // ambiguous overlapping transitions (§12.5): same event type + overlapping sourceId
    const trans = step.transitions as any[];
    for (let i = 0; i < trans.length; i++) {
      for (let j = i + 1; j < trans.length; j++) {
        const a = trans[i].on;
        const b = trans[j].on;
        if (a.type !== b.type) continue;
        const sourceOverlap = a.sourceId === undefined || b.sourceId === undefined || a.sourceId === b.sourceId;
        if (sourceOverlap) {
          add(stepPath, `step '${step.id}' has ambiguous overlapping transitions on event '${a.type}'`);
        }
      }
    }
  });

  // reachability (BFS from initialStepId over transition edges)
  const reachable = new Set<string>();
  if (stepIds.has(wf.initialStepId)) {
    const queue = [wf.initialStepId];
    reachable.add(wf.initialStepId);
    while (queue.length > 0) {
      const cur = queue.shift()!;
      const step = stepById.get(cur);
      if (!step) continue;
      for (const t of step.transitions as any[]) {
        if (stepIds.has(t.to) && !reachable.has(t.to)) {
          reachable.add(t.to);
          queue.push(t.to);
        }
      }
    }
  }
  steps.forEach((step, si) => {
    if (!reachable.has(step.id)) add(`${wfPath}.steps[${si}]`, `step '${step.id}' is unreachable from the initial step`);
  });

  // terminal reachability: every reachable step must reach a terminal (completeSlice/navigate) step
  const isTerminal = (step: any) => (step.enterActions as any[]).some((a) => a.type === "completeSlice" || a.type === "navigate");
  const canReachTerminal = new Map<string, boolean>();
  const reachesTerminal = (id: string, stack: Set<string>): boolean => {
    if (canReachTerminal.has(id)) return canReachTerminal.get(id)!;
    const step = stepById.get(id);
    if (!step) return false;
    if (isTerminal(step)) {
      canReachTerminal.set(id, true);
      return true;
    }
    if (stack.has(id)) return false; // cycle without a terminal along this path
    stack.add(id);
    let ok = false;
    for (const t of step.transitions as any[]) {
      if (stepIds.has(t.to) && reachesTerminal(t.to, stack)) {
        ok = true;
        break;
      }
    }
    stack.delete(id);
    if (ok) canReachTerminal.set(id, true);
    return ok;
  };
  steps.forEach((step, si) => {
    if (reachable.has(step.id) && !reachesTerminal(step.id, new Set())) {
      add(`${wfPath}.steps[${si}]`, `step '${step.id}' cannot reach a completion or navigation step`);
    }
  });

  // bounded cycles (§12.6): every cycle must contain a gated edge
  for (const scc of stronglyConnectedComponents(steps, stepIds)) {
    const inScc = new Set(scc);
    const hasSelfLoop = scc.length === 1 && sccHasSelfLoop(stepById.get(scc[0]!), scc[0]!);
    if (scc.length < 2 && !hasSelfLoop) continue; // trivial, no cycle
    let gated = false;
    for (const id of scc) {
      const step = stepById.get(id);
      if (!step) continue;
      for (const t of step.transitions as any[]) {
        if (inScc.has(t.to) && GATED_EVENT_TYPES.has(t.on.type)) gated = true;
      }
    }
    if (!gated) {
      add(wfPath, `cycle [${scc.join(", ")}] must be gated by a bounded assessment attempt or an explicit learner action`);
    }
  }

  return issues;
}

function sccHasSelfLoop(step: any, id: string): boolean {
  if (!step) return false;
  return (step.transitions as any[]).some((t) => t.to === id);
}

/** Tarjan's strongly-connected-components over the transition graph. */
function stronglyConnectedComponents(steps: any[], stepIds: Set<string>): string[][] {
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const onStack = new Set<string>();
  const stack: string[] = [];
  const result: string[][] = [];
  let counter = 0;
  const byId = new Map<string, any>();
  for (const s of steps) if (!byId.has(s.id)) byId.set(s.id, s);

  const strongConnect = (id: string) => {
    index.set(id, counter);
    low.set(id, counter);
    counter++;
    stack.push(id);
    onStack.add(id);
    const step = byId.get(id);
    for (const t of (step?.transitions ?? []) as any[]) {
      if (!stepIds.has(t.to)) continue;
      if (!index.has(t.to)) {
        strongConnect(t.to);
        low.set(id, Math.min(low.get(id)!, low.get(t.to)!));
      } else if (onStack.has(t.to)) {
        low.set(id, Math.min(low.get(id)!, index.get(t.to)!));
      }
    }
    if (low.get(id) === index.get(id)) {
      const comp: string[] = [];
      let w: string;
      do {
        w = stack.pop()!;
        onStack.delete(w);
        comp.push(w);
      } while (w !== id);
      result.push(comp);
    }
  };

  for (const s of steps) if (!index.has(s.id)) strongConnect(s.id);
  return result;
}
