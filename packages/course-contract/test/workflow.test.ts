import { describe, it, expect } from "vitest";
import { SliceWorkflow, WorkflowAction } from "../src/workflow";

describe("WorkflowAction", () => {
  it("parses each action variant shape", () => {
    const actions = [
      { type: "show", targetId: "q" },
      { type: "focus", target: { blockId: "img", itemId: "a" } },
      { type: "clearFocus" },
      { type: "playNarration", narrationId: "intro" },
      { type: "startTimer", timerId: "t1", durationSeconds: 5 },
      { type: "completeSlice" },
      { type: "navigate", target: "nextSlice" },
    ];
    for (const a of actions) expect(WorkflowAction.safeParse(a).success).toBe(true);
  });
  it("rejects navigate to anything but nextSlice", () => {
    expect(WorkflowAction.safeParse({ type: "navigate", target: "prevSlice" }).success).toBe(false);
  });
  it("rejects an action carrying an arbitrary payload (strict)", () => {
    expect(WorkflowAction.safeParse({ type: "show", targetId: "q", url: "http://x" }).success).toBe(false);
  });
});

describe("SliceWorkflow", () => {
  it("parses a minimal one-step workflow", () => {
    const wf = { version: "1.0", initialStepId: "s1", steps: [ { id: "s1", enterActions: [], transitions: [] } ] };
    expect(SliceWorkflow.safeParse(wf).success).toBe(true);
  });
});
