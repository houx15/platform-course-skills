import { describe, it, expect } from "vitest";
import type { BlockSessionState, SliceDefinition, SliceSessionState } from "@mind-imprint/course-contract";
import { initSliceState, applyEffect, applyEvent, setCurrentWorkflowStep } from "../src/sessionState";
import { sampleSlice } from "./support";

/** Non-optional block-state accessor (the record is `V | undefined` under noUncheckedIndexedAccess). */
function blk(state: SliceSessionState, id: string): BlockSessionState {
  const s = state.blockStates[id];
  if (!s) throw new Error(`no block state for '${id}'`);
  return s;
}

function threeBlockSlice(initialState?: SliceDefinition["workflow"]["initialState"]): SliceDefinition {
  const base = sampleSlice();
  return {
    ...base,
    blocks: [
      { id: "a", type: "text", content: "A" },
      { id: "b", type: "text", content: "B" },
      {
        id: "q",
        type: "singleChoice",
        prompt: "pick",
        options: [
          { id: "x", label: "X" },
          { id: "y", label: "Y" },
        ],
        assessment: { mode: "graded", correctOptionId: "x" },
        completion: { rule: "submit-correct" },
      },
    ],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["a", "b", "q"] }] },
    workflow: { ...base.workflow, initialState },
  };
}

describe("initSliceState", () => {
  it("defaults everything visible + enabled when no initialState", () => {
    const state = initSliceState(threeBlockSlice(undefined));
    expect(state.status).toBe("not-started");
    expect(state.elapsedSeconds).toBe(0);
    expect(blk(state, "a")).toEqual({ visible: true, enabled: true, completed: false });
    expect(blk(state, "b")).toEqual({ visible: true, enabled: true, completed: false });
    // assessment blocks seed attempts:0
    expect(blk(state, "q")).toEqual({ visible: true, enabled: true, completed: false, attempts: 0 });
  });

  it("applies visibleBlockIds / enabledBlockIds: listed visible, empty-enabled = all disabled", () => {
    const state = initSliceState(threeBlockSlice({ visibleBlockIds: ["a"], enabledBlockIds: [] }));
    expect(blk(state, "a").visible).toBe(true);
    expect(blk(state, "b").visible).toBe(false);
    expect(blk(state, "q").visible).toBe(false);
    expect(blk(state, "a").enabled).toBe(false);
    expect(blk(state, "b").enabled).toBe(false);
    expect(blk(state, "q").enabled).toBe(false);
  });

  it("omitting a single list preserves that list's default", () => {
    // visibleBlockIds present, enabledBlockIds omitted → visibility restricted, all still enabled
    const state = initSliceState(threeBlockSlice({ visibleBlockIds: ["a"] }));
    expect(blk(state, "b").visible).toBe(false);
    expect(blk(state, "a").enabled).toBe(true);
    expect(blk(state, "b").enabled).toBe(true);
  });
});

describe("applyEffect", () => {
  const base = () => initSliceState(threeBlockSlice({ visibleBlockIds: ["a"], enabledBlockIds: [] }));

  it("show/hide flip visibility; enable/disable flip enabled", () => {
    const s0 = base();
    const s1 = applyEffect(s0, { type: "show", targetId: "b" });
    expect(blk(s1, "b").visible).toBe(true);
    // immutability: original unchanged
    expect(blk(s0, "b").visible).toBe(false);

    const s2 = applyEffect(s1, { type: "enable", targetId: "q" });
    expect(blk(s2, "q").enabled).toBe(true);
    const s3 = applyEffect(s2, { type: "hide", targetId: "a" });
    expect(blk(s3, "a").visible).toBe(false);
    const s4 = applyEffect(s3, { type: "disable", targetId: "q" });
    expect(blk(s4, "q").enabled).toBe(false);
  });

  it("resetBlock clears completion/attempts/answer", () => {
    let s = base();
    s = applyEvent(s, { type: "answer.submitted", sourceId: "q", payload: { value: "x" } });
    s = applyEvent(s, { type: "answer.correct", sourceId: "q", payload: null });
    expect(blk(s, "q").completed).toBe(true);
    const reset = applyEffect(s, { type: "resetBlock", targetId: "q" });
    expect(blk(reset, "q").completed).toBe(false);
    expect(blk(reset, "q").attempts).toBe(0);
    expect(blk(reset, "q").answer).toBeUndefined();
  });

  it("completeSlice moves slice status to completed", () => {
    const s = applyEffect(base(), { type: "completeSlice" });
    expect(s.status).toBe("completed");
  });

  it("completeSlice stamps completedAt and freezes elapsedSeconds when occurredAt is given", () => {
    let s = base();
    s = applyEvent(s, { type: "answer.submitted", sourceId: "q", payload: { value: "x" }, occurredAt: "2026-08-16T00:00:00.000Z" });
    expect(s.startedAt).toBe("2026-08-16T00:00:00.000Z");
    expect(s.status).toBe("in-progress");

    s = applyEffect(s, { type: "completeSlice" }, "2026-08-16T00:00:10.000Z");
    expect(s.status).toBe("completed");
    expect(s.completedAt).toBe("2026-08-16T00:00:10.000Z");
    expect(s.elapsedSeconds).toBe(10);
  });

  it("completeSlice without occurredAt leaves completedAt/elapsedSeconds untouched", () => {
    const s = applyEffect(base(), { type: "completeSlice" });
    expect(s.completedAt).toBeUndefined();
    expect(s.elapsedSeconds).toBe(0);
  });

  it("transient effects (focus/narration/timer/play) leave persisted state unchanged", () => {
    const s0 = base();
    for (const effect of [
      { type: "focus", target: { blockId: "a" } },
      { type: "clearFocus" },
      { type: "playNarration", narrationId: "introduce-video" },
      { type: "playBlock", targetId: "a" },
      { type: "startTimer", timerId: "t1", durationSeconds: 5 },
      { type: "navigate", target: "nextSlice" },
    ] as const) {
      expect(applyEffect(s0, effect)).toEqual(s0);
    }
  });

  it("throws on an effect targeting an unknown block", () => {
    expect(() => applyEffect(base(), { type: "show", targetId: "ghost" })).toThrow();
  });
});

describe("applyEvent", () => {
  const base = () => initSliceState(threeBlockSlice(undefined));

  it("answer.submitted increments attempts and stores payload.value (P2-02 fix)", () => {
    const s0 = base();
    const s1 = applyEvent(s0, { type: "answer.submitted", sourceId: "q", payload: { value: "y" } });
    expect(blk(s1, "q").attempts).toBe(1);
    expect(blk(s1, "q").answer).toBe("y");
    expect(blk(s0, "q").attempts).toBe(0); // immutability

    const s2 = applyEvent(s1, { type: "answer.submitted", sourceId: "q", payload: { value: "x" } });
    expect(blk(s2, "q").attempts).toBe(2);
    expect(blk(s2, "q").answer).toBe("x");
  });

  it("regression: the old buggy payload.answer field is no longer read", () => {
    // Emitters send `{ value }` (SingleChoiceRenderer/FillBlankRenderer); a
    // payload shaped like the pre-fix assumption `{ answer }` must NOT populate
    // `answer` — this is exactly the P2-02 bug (real submissions silently
    // stored `undefined`).
    const s = applyEvent(base(), { type: "answer.submitted", sourceId: "q", payload: { answer: "y" } });
    expect(blk(s, "q").answer).toBeUndefined();
    expect(blk(s, "q").attempts).toBe(1); // attempts still increments even with a malformed payload
  });

  it("answer.correct / block.completed mark the source block completed", () => {
    const correct = applyEvent(base(), { type: "answer.correct", sourceId: "q", payload: null });
    expect(blk(correct, "q").completed).toBe(true);
    const done = applyEvent(base(), { type: "block.completed", sourceId: "a", payload: null });
    expect(blk(done, "a").completed).toBe(true);
  });

  it("video.paused / video.ended record media position", () => {
    const s = applyEvent(base(), { type: "video.paused", sourceId: "a", payload: { positionSeconds: 12.5 } });
    expect(blk(s, "a").mediaPositionSeconds).toBe(12.5);
  });

  it("interaction.completed / video.interaction.completed populate interactionResult", () => {
    const s = applyEvent(base(), {
      type: "interaction.completed",
      sourceId: "a",
      payload: { interactionId: "cue-1", result: { correct: true, value: "b" } },
    });
    expect(blk(s, "a").interactionResult).toEqual({ "cue-1": { correct: true, value: "b" } });
  });

  it("interaction.completed / video.interaction.completed merge by interactionId instead of clobbering", () => {
    let s = base();
    s = applyEvent(s, {
      type: "video.interaction.completed",
      sourceId: "a",
      payload: { interactionId: "cue-1", result: { correct: true } },
    });
    s = applyEvent(s, {
      type: "video.interaction.completed",
      sourceId: "a",
      payload: { interactionId: "cue-2", result: { correct: false } },
    });
    expect(blk(s, "a").interactionResult).toEqual({
      "cue-1": { correct: true },
      "cue-2": { correct: false },
    });
  });

  it("ignores events whose source is not a block (e.g. narration.ended)", () => {
    const s0 = base();
    expect(applyEvent(s0, { type: "narration.ended", sourceId: "introduce-video", payload: null })).toEqual(s0);
  });

  it("stamps slice timing from occurredAt: first event → in-progress + startedAt, later events recompute elapsedSeconds", () => {
    let s = base();
    expect(s.status).toBe("not-started");

    s = applyEvent(s, { type: "block.completed", sourceId: "a", payload: null, occurredAt: "2026-08-16T00:00:00.000Z" });
    expect(s.status).toBe("in-progress");
    expect(s.startedAt).toBe("2026-08-16T00:00:00.000Z");
    expect(s.elapsedSeconds).toBe(0);

    s = applyEvent(s, { type: "video.paused", sourceId: "b", payload: null, occurredAt: "2026-08-16T00:00:05.000Z" });
    expect(s.startedAt).toBe("2026-08-16T00:00:00.000Z"); // startedAt doesn't move
    expect(s.elapsedSeconds).toBe(5);
  });

  it("events with no occurredAt leave slice timing untouched", () => {
    const s0 = base();
    const s1 = applyEvent(s0, { type: "block.completed", sourceId: "a", payload: null });
    expect(s1.status).toBe("not-started");
    expect(s1.startedAt).toBeUndefined();
  });

  it("touches slice timing even for events whose source is not a block", () => {
    const s = applyEvent(base(), {
      type: "narration.ended",
      sourceId: "introduce-video",
      payload: null,
      occurredAt: "2026-08-16T00:00:00.000Z",
    });
    expect(s.status).toBe("in-progress");
    expect(s.startedAt).toBe("2026-08-16T00:00:00.000Z");
  });
});

describe("setCurrentWorkflowStep", () => {
  it("records the current workflow step id", () => {
    const s0 = initSliceState(threeBlockSlice(undefined));
    expect(s0.currentWorkflowStepId).toBeUndefined();
    const s1 = setCurrentWorkflowStep(s0, "wait-for-answer");
    expect(s1.currentWorkflowStepId).toBe("wait-for-answer");
    expect(s0.currentWorkflowStepId).toBeUndefined(); // immutability
  });

  it("is a no-op (same reference) when the step id is unchanged", () => {
    const s0 = setCurrentWorkflowStep(initSliceState(threeBlockSlice(undefined)), "wait-for-answer");
    const s1 = setCurrentWorkflowStep(s0, "wait-for-answer");
    expect(s1).toBe(s0);
  });
});
