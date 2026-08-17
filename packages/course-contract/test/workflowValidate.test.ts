import { describe, it, expect } from "vitest";
import { validateSliceWorkflow } from "../src/validate/workflow";
import { validCourse } from "./fixtures";
import type { SliceDefinition } from "../src/course";

const golden = () => structuredClone(validCourse.parts[0]!.slices[0]!);
/** slice-compare-images: has a real `images` block with real item ids. */
const imagesSlice = () => structuredClone(validCourse.parts[0]!.slices[2]!);
const msgs = (xs: { message: string }[]) => xs.map((x) => x.message).join(" | ");

describe("validateSliceWorkflow", () => {
  it("passes on the golden slice", () => {
    expect(validateSliceWorkflow(validCourse.parts[0]!.slices[0]!, "s")).toEqual([]);
  });
  it("flags a transition to a missing step", () => {
    const s = golden();
    s.workflow.steps[0]!.transitions.push({ on: { type: "student.continue" }, to: "nowhere" });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/unknown step 'nowhere'/i);
  });
  it("flags an unreachable step", () => {
    const s = golden();
    s.workflow.steps.push({ id: "orphan", enterActions: [], transitions: [] });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/unreachable/i);
  });
  it("flags a playNarration referencing an undeclared narration", () => {
    const s = golden();
    s.workflow.steps[0]!.enterActions.push({ type: "playNarration", narrationId: "ghost" });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/narration 'ghost'/i);
  });
  it("flags ambiguous overlapping transitions", () => {
    const s = golden();
    const step = s.workflow.steps[0]!;
    step.transitions = [
      { on: { type: "student.continue" }, to: step.id === s.workflow.initialStepId ? s.workflow.steps[1]!.id : s.workflow.initialStepId },
      { on: { type: "student.continue" }, to: s.workflow.steps[1]!.id },
    ];
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/ambiguous/i);
  });
});

// ---------------------------------------------------------------------------
// P2-01 gap 1 — initial-state references (visibleBlockIds/enabledBlockIds/focusedTarget)
// ---------------------------------------------------------------------------
describe("validateSliceWorkflow — initial-state references (P2-01 gap 1)", () => {
  it("passes initial-state references to real blocks and a real focused item", () => {
    const s = imagesSlice();
    s.workflow.initialState = {
      visibleBlockIds: ["evidence-images"],
      enabledBlockIds: ["evidence-reflection"],
      focusedTarget: { blockId: "evidence-images", itemId: "cropped-chart" },
    };
    expect(validateSliceWorkflow(s, "s")).toEqual([]);
  });
  it("flags an initial-state visibleBlockIds reference to an unknown block", () => {
    const s = golden();
    s.workflow.initialState = { visibleBlockIds: ["ghost"] };
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/initial state references unknown block 'ghost'/i);
  });
  it("flags an initial-state enabledBlockIds reference to an unknown block", () => {
    const s = golden();
    s.workflow.initialState = { enabledBlockIds: ["ghost"] };
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/initial state references unknown block 'ghost'/i);
  });
  it("flags an initial-state focusedTarget referencing an unknown block", () => {
    const s = imagesSlice();
    s.workflow.initialState = { focusedTarget: { blockId: "ghost" } };
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/initial state focus references unknown block 'ghost'/i);
  });
  it("flags an initial-state focusedTarget referencing an unknown item", () => {
    const s = imagesSlice();
    s.workflow.initialState = { focusedTarget: { blockId: "evidence-images", itemId: "ghost-item" } };
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/initial state focus references unknown item 'ghost-item'/i);
  });
});

// ---------------------------------------------------------------------------
// P2-01 gap 2 — producer-aware event source / interaction / timer references
// ---------------------------------------------------------------------------
describe("validateSliceWorkflow — producer-aware event references (P2-01 gap 2)", () => {
  it("passes a transition sourced from a block that can really produce that event (video.started ← video block)", () => {
    const s = golden();
    s.workflow.steps[0]!.transitions.push({ on: { type: "video.started", sourceId: "case-video" }, to: "watch-video" });
    expect(validateSliceWorkflow(s, "s")).toEqual([]);
  });
  it("passes a timer.elapsed transition whose timerId was started in this workflow", () => {
    const s = golden();
    s.workflow.steps[0]!.enterActions.push({ type: "startTimer", timerId: "t1", durationSeconds: 5 });
    s.workflow.steps[0]!.transitions.push({ on: { type: "timer.elapsed", timerId: "t1" }, to: "watch-video" });
    expect(validateSliceWorkflow(s, "s")).toEqual([]);
  });
  it("flags an event sourceId referencing a nonexistent block", () => {
    const s = golden();
    s.workflow.steps[0]!.transitions.push({ on: { type: "answer.correct", sourceId: "ghost" }, to: "watch-video" });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/sourceId references unknown block 'ghost'/i);
  });
  it("flags an event sourceId whose block cannot produce that event type (video.started on a singleChoice block)", () => {
    const s = golden();
    s.workflow.steps[0]!.transitions.push({ on: { type: "video.started", sourceId: "comparison-question" }, to: "watch-video" });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/cannot be produced by block 'comparison-question'/i);
  });
  it("flags a timer.elapsed transition whose timerId was never started", () => {
    const s = golden();
    s.workflow.steps[0]!.transitions.push({ on: { type: "timer.elapsed", timerId: "ghost-timer" }, to: "watch-video" });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/timerId references timer 'ghost-timer' that is never started/i);
  });
  it("flags an interactionId on an event that never carries one", () => {
    const s = golden();
    (s.workflow.steps[0]!.transitions[0]!.on as any).interactionId = "x";
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/interactionId is not meaningful for event 'narration.ended'/i);
  });
});

// ---------------------------------------------------------------------------
// P2-01 gap 3 — matcher overlap: full field intersection, not just type+sourceId
// ---------------------------------------------------------------------------

/** A minimal, otherwise-valid slice with a video block that owns a cue-based interaction. */
function cueSlice(): SliceDefinition {
  return {
    id: "cue-slice",
    title: "Cue slice",
    objectiveIds: [],
    estimatedSeconds: 60,
    blocks: [
      { id: "cue-video", type: "video", source: "assets/videos/cue.mp4", interaction: { source: "interactions/video/cue.json" } },
    ],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["cue-video"] }] },
    narrations: [],
    workflow: {
      version: "1.0",
      initialStepId: "watch",
      steps: [
        {
          id: "watch",
          enterActions: [],
          transitions: [
            { on: { type: "video.interaction.completed", sourceId: "cue-video", interactionId: "cue-a" }, to: "after-a" },
            { on: { type: "video.interaction.completed", sourceId: "cue-video", interactionId: "cue-b" }, to: "after-b" },
          ],
        },
        { id: "after-a", enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }], transitions: [] },
        { id: "after-b", enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }], transitions: [] },
      ],
    },
    navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
  };
}

describe("validateSliceWorkflow — matcher overlap is the full field intersection (P2-01 gap 3)", () => {
  it("passes disjoint cue transitions that share type+sourceId but differ by interactionId", () => {
    expect(validateSliceWorkflow(cueSlice(), "s")).toEqual([]);
  });
  it("flags transitions whose matchers are truly identical (same type+sourceId+interactionId)", () => {
    const s = cueSlice();
    (s.workflow.steps[0]!.transitions[1]!.on as any).interactionId = "cue-a";
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/ambiguous/i);
  });
});

// ---------------------------------------------------------------------------
// P2-01 gap 4 — required-completion dominance (no bypass route to `navigate`)
// ---------------------------------------------------------------------------
describe("validateSliceWorkflow — required-completion dominance (P2-01 gap 4)", () => {
  it("passes a workflow whose only routes to navigate go through both required completion gates", () => {
    expect(validateSliceWorkflow(golden(), "s")).toEqual([]);
  });
  it("flags a navigate step reachable without a required block completion firing (bypass edge)", () => {
    const s = golden();
    // `introduce-question` (index 2) gains a shortcut straight to the terminal
    // `next` step, skipping `wait-for-answer` — the graded question's gate.
    s.workflow.steps[2]!.transitions.push({ on: { type: "student.continue" }, to: "next" });
    expect(msgs(validateSliceWorkflow(s, "s"))).toMatch(/block 'comparison-question' has a required completion that can be bypassed/i);
  });
});

// ---------------------------------------------------------------------------
// P2-01 gap 5 — bounded cycles: a proven exit, not merely a suggestive event label
// ---------------------------------------------------------------------------

/** A cycle whose only way out is the learner explicitly choosing to continue. */
function studentActionBoundedSlice(): SliceDefinition {
  return {
    id: "loop-slice",
    title: "Loop slice",
    objectiveIds: [],
    estimatedSeconds: 60,
    blocks: [{ id: "lead", type: "text", content: "Some content." }],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["lead"] }] },
    narrations: [
      { id: "n1", text: "First.", audio: "assets/audio/n1.mp3" },
      { id: "n2", text: "Second.", audio: "assets/audio/n2.mp3" },
    ],
    workflow: {
      version: "1.0",
      initialStepId: "loop-a",
      steps: [
        {
          id: "loop-a",
          enterActions: [{ type: "playNarration", narrationId: "n1" }],
          transitions: [
            { on: { type: "narration.ended", sourceId: "n1" }, to: "loop-b" },
            { on: { type: "student.continue" }, to: "done" },
          ],
        },
        {
          id: "loop-b",
          enterActions: [{ type: "playNarration", narrationId: "n2" }],
          transitions: [{ on: { type: "narration.ended", sourceId: "n2" }, to: "loop-a" }],
        },
        { id: "done", enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }], transitions: [] },
      ],
    },
    navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
  };
}

/** A graded single-choice remediation loop with NO attempt cap — genuinely unbounded. */
function unboundedRemediationSlice(): SliceDefinition {
  return {
    id: "unbounded-slice",
    title: "Unbounded remediation",
    objectiveIds: [],
    estimatedSeconds: 60,
    blocks: [
      {
        id: "q1",
        type: "singleChoice",
        prompt: "Pick one",
        options: [
          { id: "a", label: "A" },
          { id: "b", label: "B" },
        ],
        assessment: { mode: "graded", correctOptionId: "a" },
        completion: { rule: "submit-correct" },
      },
    ],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["q1"] }] },
    narrations: [{ id: "remed", text: "Try again.", audio: "assets/audio/remed.mp3" }],
    workflow: {
      version: "1.0",
      initialStepId: "wait-for-answer",
      steps: [
        {
          id: "wait-for-answer",
          enterActions: [],
          transitions: [
            { on: { type: "answer.correct", sourceId: "q1" }, to: "done" },
            { on: { type: "answer.incorrect", sourceId: "q1" }, to: "remediate" },
          ],
        },
        {
          id: "remediate",
          enterActions: [{ type: "playNarration", narrationId: "remed" }],
          transitions: [{ on: { type: "narration.ended", sourceId: "remed" }, to: "wait-for-answer" }],
        },
        { id: "done", enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }], transitions: [] },
      ],
    },
    navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
  };
}

describe("validateSliceWorkflow — bounded cycles (P2-01 gap 5)", () => {
  it("passes the golden's attempt-capped remediation cycle (submit-correct-or-exhausted)", () => {
    expect(validateSliceWorkflow(golden(), "s")).toEqual([]);
  });
  it("passes a cycle bounded by an explicit learner action (student.continue exit)", () => {
    expect(validateSliceWorkflow(studentActionBoundedSlice(), "s")).toEqual([]);
  });
  it("flags an unbounded submit-correct remediation cycle (no attempt cap, no explicit-action exit)", () => {
    expect(msgs(validateSliceWorkflow(unboundedRemediationSlice(), "s"))).toMatch(
      /must be gated by a bounded assessment attempt or an explicit learner action/i,
    );
  });
});
