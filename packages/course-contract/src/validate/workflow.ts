import type { SliceDefinition } from "../course";
import type { ValidationIssue } from "./types";

/** Actions that require a video block target (§12.3). */
const VIDEO_ONLY_ACTIONS = new Set(["playBlock", "pauseBlock", "resetBlock"]);
/** Actions whose `targetId` addresses a block. */
const BLOCK_TARGET_ACTIONS = new Set(["show", "hide", "enable", "disable", "playBlock", "pauseBlock", "resetBlock"]);
/** Narration actions whose `narrationId` addresses a declared narration. */
const NARRATION_ACTIONS = new Set(["playNarration", "pauseNarration", "stopNarration"]);

/**
 * A matcher's `interactionId` is only meaningful for events that actually
 * carry one at runtime: the two video-interaction cue events, and
 * `interaction.completed` (whose payload's `interactionId` is host-stamped to
 * the owning block id — see `HtmlInteractionRenderer`).
 */
const INTERACTION_ID_EVENTS = new Set(["video.interaction.shown", "video.interaction.completed", "interaction.completed"]);

/**
 * §12.4/§12.6 — which block/narration/timer kind can legitimately PRODUCE
 * each WorkflowEventType, keyed by `sourceId`'s referent. Mirrors the actual
 * renderer emitters (course-renderer `*Renderer.tsx`) so a transition can
 * only wait on an event its own slice can really emit. `narration.ended`'s
 * `sourceId` is a narration id (not a block id); `timer.elapsed`'s `sourceId`
 * is the timer id the enclosing step started (`SlicePlayer.tsx`); a bare
 * learner-driven `student.continue` has no authored id to check against.
 */
type EventProducer =
  | { kind: "narration" }
  | { kind: "block"; types: readonly string[]; requiresInteraction?: boolean }
  | { kind: "timer" }
  | { kind: "none" };

const EVENT_PRODUCERS: Record<string, EventProducer> = {
  "narration.ended": { kind: "narration" },
  "video.started": { kind: "block", types: ["video"] },
  "video.paused": { kind: "block", types: ["video"] },
  "video.ended": { kind: "block", types: ["video"] },
  "video.interaction.shown": { kind: "block", types: ["video"], requiresInteraction: true },
  "video.interaction.completed": { kind: "block", types: ["video"], requiresInteraction: true },
  "pdf.opened": { kind: "block", types: ["pdf"] },
  "pdf.pageChanged": { kind: "block", types: ["pdf"] },
  "interaction.completed": { kind: "block", types: ["interactiveHtml"] },
  "answer.submitted": { kind: "block", types: ["singleChoice", "fillBlank"] },
  "answer.correct": { kind: "block", types: ["singleChoice", "fillBlank"] },
  "answer.incorrect": { kind: "block", types: ["singleChoice", "fillBlank"] },
  "answer.attemptsExhausted": { kind: "block", types: ["singleChoice", "fillBlank"] },
  "block.completed": { kind: "block", types: ["video", "interactiveHtml", "singleChoice", "fillBlank"] },
  "student.continue": { kind: "none" },
  "timer.elapsed": { kind: "timer" },
};

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
  const blockById = new Map<string, any>();
  for (const b of slice.blocks as any[]) blockById.set(b.id, b);
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

  // initial-state references (§12.6): visible/enabled blocks and the focused target must be real
  if (wf.initialState) {
    const isPath = `${wfPath}.initialState`;
    (wf.initialState.visibleBlockIds ?? []).forEach((bid: string, i: number) => {
      if (!blockIds.has(bid)) add(`${isPath}.visibleBlockIds[${i}]`, `initial state references unknown block '${bid}'`);
    });
    (wf.initialState.enabledBlockIds ?? []).forEach((bid: string, i: number) => {
      if (!blockIds.has(bid)) add(`${isPath}.enabledBlockIds[${i}]`, `initial state references unknown block '${bid}'`);
    });
    const ft = wf.initialState.focusedTarget as any;
    if (ft) {
      if (!blockIds.has(ft.blockId)) {
        add(`${isPath}.focusedTarget`, `initial state focus references unknown block '${ft.blockId}'`);
      } else if (ft.itemId !== undefined) {
        const items = imageItemIds.get(ft.blockId);
        if (!items || !items.has(ft.itemId)) {
          add(`${isPath}.focusedTarget`, `initial state focus references unknown item '${ft.itemId}' in block '${ft.blockId}'`);
        }
      }
    }
  }

  // per-step: action targets, transition targets/sources, terminal/navigate rule, ambiguity
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

    // transition targets + event source/interaction/timer references (§12.4/§12.6)
    (step.transitions as any[]).forEach((t, ti) => {
      const tPath = `${stepPath}.transitions[${ti}]`;
      if (!stepIds.has(t.to)) add(tPath, `transition references unknown step '${t.to}'`);

      const on = t.on;
      const onPath = `${tPath}.on`;
      const producer = EVENT_PRODUCERS[on.type];
      if (on.sourceId !== undefined && producer) {
        if (producer.kind === "narration") {
          if (!narrationIds.has(on.sourceId)) add(onPath, `event '${on.type}' sourceId references unknown narration '${on.sourceId}'`);
        } else if (producer.kind === "block") {
          const block = blockById.get(on.sourceId);
          if (!block) {
            add(onPath, `event '${on.type}' sourceId references unknown block '${on.sourceId}'`);
          } else if (!producer.types.includes(block.type)) {
            add(onPath, `event '${on.type}' cannot be produced by block '${on.sourceId}' (type '${block.type}')`);
          } else if (producer.requiresInteraction && !block.interaction) {
            add(onPath, `event '${on.type}' sourceId '${on.sourceId}' has no interaction configured`);
          }
        } else if (producer.kind === "timer") {
          if (!declaredTimerIds.has(on.sourceId)) add(onPath, `event '${on.type}' sourceId references timer '${on.sourceId}' that is never started`);
        }
      }
      if (on.interactionId !== undefined && !INTERACTION_ID_EVENTS.has(on.type)) {
        add(onPath, `interactionId is not meaningful for event '${on.type}'`);
      }
      if (on.timerId !== undefined && !declaredTimerIds.has(on.timerId)) {
        add(onPath, `timerId references timer '${on.timerId}' that is never started`);
      }
    });

    // ambiguous overlapping transitions (§12.5): matchers ambiguous only if they
    // can both match the same event — the full field intersection, not just
    // type+sourceId (that under/over-reports against interactionId/timerId cues).
    const trans = step.transitions as any[];
    for (let i = 0; i < trans.length; i++) {
      for (let j = i + 1; j < trans.length; j++) {
        if (matchersOverlap(trans[i].on, trans[j].on)) {
          add(stepPath, `step '${step.id}' has ambiguous overlapping transitions on event '${trans[i].on.type}'`);
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

  // required-completion dominance (§12.6): for every block whose completion this
  // workflow actually gates on (≥1 transition matches a genuinely completing
  // event for that block), a `navigate` step must be UNREACHABLE once those
  // exact gating transitions are removed — i.e. there is no other route to
  // `navigate` that bypasses the gate.
  const hasNavigateAction = (step: any) => (step.enterActions as any[]).some((a) => a.type === "navigate");
  for (const block of slice.blocks as any[]) {
    const completionTypes = completionEventTypesFor(block);
    if (!completionTypes) continue;
    const removed = new Set<string>();
    steps.forEach((step) => {
      (step.transitions as any[]).forEach((t, ti) => {
        if (t.on.sourceId === block.id && completionTypes.has(t.on.type)) removed.add(`${step.id}#${ti}`);
      });
    });
    if (removed.size === 0) continue; // this slice's workflow never gates on this block — nothing to prove

    const seen = new Set<string>();
    if (stepIds.has(wf.initialStepId)) {
      const queue = [wf.initialStepId];
      seen.add(wf.initialStepId);
      while (queue.length > 0) {
        const cur = queue.shift()!;
        const step = stepById.get(cur);
        if (!step) continue;
        (step.transitions as any[]).forEach((t, ti) => {
          if (removed.has(`${cur}#${ti}`)) return; // this is the gate — do not traverse it
          if (stepIds.has(t.to) && !seen.has(t.to)) {
            seen.add(t.to);
            queue.push(t.to);
          }
        });
      }
    }
    const bypassed = steps.some((step) => seen.has(step.id) && hasNavigateAction(step));
    if (bypassed) {
      add(wfPath, `block '${block.id}' has a required completion that can be bypassed — a 'navigate' step is reachable without it firing`);
    }
  }

  // bounded cycles (§12.6): every cycle must have a proven bounded EXIT — an
  // attempt-capped assessment exhaustion or an explicit learner action/timer —
  // not merely contain one of those event labels somewhere inside the loop.
  for (const scc of stronglyConnectedComponents(steps, stepIds)) {
    const inScc = new Set(scc);
    const hasSelfLoop = scc.length === 1 && sccHasSelfLoop(stepById.get(scc[0]!), scc[0]!);
    if (scc.length < 2 && !hasSelfLoop) continue; // trivial, no cycle
    let bounded = false;
    outer: for (const id of scc) {
      const step = stepById.get(id);
      if (!step) continue;
      for (const t of step.transitions as any[]) {
        if (inScc.has(t.to)) continue; // a loop edge keeps the cycle alive; only an exit can bound it
        const on = t.on;
        if (on.type === "student.continue" || on.type === "timer.elapsed") {
          bounded = true;
          break outer;
        }
        if (on.type === "answer.attemptsExhausted") {
          const block = blockById.get(on.sourceId);
          if (block && (block.type === "singleChoice" || block.type === "fillBlank") && block.completion?.rule === "submit-correct-or-exhausted") {
            bounded = true;
            break outer;
          }
        }
      }
    }
    if (!bounded) {
      add(wfPath, `cycle [${scc.join(", ")}] must be gated by a bounded assessment attempt or an explicit learner action`);
    }
  }

  return issues;
}

/** True iff two matchers CAN both match the same runtime event: same `type`, and no field where both declare different values. */
function matchersOverlap(a: any, b: any): boolean {
  if (a.type !== b.type) return false;
  for (const f of ["sourceId", "interactionId", "timerId"] as const) {
    if (a[f] !== undefined && b[f] !== undefined && a[f] !== b[f]) return false;
  }
  return true;
}

/**
 * The event types that reliably signal a block has TRULY completed, per the
 * renderer's own emission logic (`evaluateSubmission`, `VideoRenderer`,
 * `HtmlInteractionRenderer`) — generous by design (includes every event a
 * completing submission can produce, not just the narrowest one) so a
 * dominance check never treats an unrelated attempt-retry edge as a bypass.
 * `null` means the block has no reliable completion signal to gate on (no
 * `completion` configured, or a block kind that never completes).
 */
function completionEventTypesFor(block: any): Set<string> | null {
  switch (block.type) {
    case "video":
      return block.completion ? new Set(["block.completed"]) : null;
    case "interactiveHtml":
      return block.completion?.rule === "interaction-complete" ? new Set(["interaction.completed", "block.completed"]) : null;
    case "singleChoice":
    case "fillBlank":
      return new Set(["answer.correct", "answer.attemptsExhausted", "answer.submitted", "block.completed"]);
    default:
      return null;
  }
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
