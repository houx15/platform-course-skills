import { describe, it, expect } from "vitest";
import { WorkflowRuntime, WorkflowRuntimeError, replay } from "../src/workflowRuntime";
import { sampleWorkflow } from "./support";

describe("WorkflowRuntime", () => {
  it("start() enters the initial step and returns its enterActions in order", () => {
    const rt = new WorkflowRuntime(sampleWorkflow());
    const effects = rt.start();
    expect(rt.currentStepId).toBe("introduce");
    expect(effects).toEqual([
      { type: "focus", target: { blockId: "case-video" } },
      { type: "playNarration", narrationId: "introduce-video" },
    ]);
  });

  it("throws if start() is called twice", () => {
    const rt = new WorkflowRuntime(sampleWorkflow());
    rt.start();
    expect(() => rt.start()).toThrow(WorkflowRuntimeError);
  });

  it("a matching event advances to the target step and returns its enterActions", () => {
    const rt = new WorkflowRuntime(sampleWorkflow());
    rt.start();
    const effects = rt.send({ type: "narration.ended", sourceId: "introduce-video" });
    expect(rt.currentStepId).toBe("watch-video");
    expect(effects).toEqual([
      { type: "enable", targetId: "case-video" },
      { type: "playBlock", targetId: "case-video" },
    ]);
  });

  it("a non-matching event returns [] and leaves the current step unchanged", () => {
    const rt = new WorkflowRuntime(sampleWorkflow());
    rt.start();
    // wrong sourceId → no matcher matches
    const effects = rt.send({ type: "narration.ended", sourceId: "some-other-narration" });
    expect(effects).toEqual([]);
    expect(rt.currentStepId).toBe("introduce");
    // wrong type → no matcher matches
    expect(rt.send({ type: "answer.correct", sourceId: "introduce-video" })).toEqual([]);
    expect(rt.currentStepId).toBe("introduce");
  });

  it("branches: answer.incorrect → remediate, answer.correct → summarize", () => {
    const drive = (branch: { type: any; sourceId: string }) => {
      const rt = new WorkflowRuntime(sampleWorkflow());
      rt.start();
      rt.send({ type: "narration.ended", sourceId: "introduce-video" });
      rt.send({ type: "block.completed", sourceId: "case-video" });
      rt.send({ type: "narration.ended", sourceId: "introduce-question" });
      expect(rt.currentStepId).toBe("wait-for-answer");
      const effects = rt.send(branch);
      return { rt, effects };
    };

    const incorrect = drive({ type: "answer.incorrect", sourceId: "comparison-question" });
    expect(incorrect.rt.currentStepId).toBe("remediate");
    expect(incorrect.effects[0]).toEqual({ type: "disable", targetId: "comparison-question" });

    const correct = drive({ type: "answer.correct", sourceId: "comparison-question" });
    expect(correct.rt.currentStepId).toBe("summarize");
    expect(correct.effects).toEqual([
      { type: "clearFocus" },
      { type: "playNarration", narrationId: "slice-summary" },
    ]);
  });

  it("reaches a terminal step whose enterActions complete + navigate", () => {
    const rt = new WorkflowRuntime(sampleWorkflow());
    rt.start();
    rt.send({ type: "narration.ended", sourceId: "introduce-video" });
    rt.send({ type: "block.completed", sourceId: "case-video" });
    rt.send({ type: "narration.ended", sourceId: "introduce-question" });
    rt.send({ type: "answer.correct", sourceId: "comparison-question" });
    const effects = rt.send({ type: "narration.ended", sourceId: "slice-summary" });
    expect(rt.currentStepId).toBe("next");
    expect(rt.isTerminal).toBe(true);
    expect(effects).toEqual([{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }]);
  });

  it("send() before start() throws WorkflowRuntimeError", () => {
    const rt = new WorkflowRuntime(sampleWorkflow());
    expect(() => rt.send({ type: "narration.ended", sourceId: "introduce-video" })).toThrow(WorkflowRuntimeError);
  });

  it("restoreStepId enters a mid-workflow step on start()", () => {
    const rt = new WorkflowRuntime(sampleWorkflow(), { restoreStepId: "wait-for-answer" });
    const effects = rt.start();
    expect(rt.currentStepId).toBe("wait-for-answer");
    expect(effects).toEqual([{ type: "enable", targetId: "comparison-question" }]);
  });

  it("start with an unknown restoreStepId throws", () => {
    const rt = new WorkflowRuntime(sampleWorkflow(), { restoreStepId: "no-such-step" });
    expect(() => rt.start()).toThrow(WorkflowRuntimeError);
  });

  it("replay is deterministic: same event stream yields identical effects and final step", () => {
    const events = [
      { type: "narration.ended" as const, sourceId: "introduce-video" },
      { type: "block.completed" as const, sourceId: "case-video" },
      { type: "narration.ended" as const, sourceId: "introduce-question" },
      { type: "answer.incorrect" as const, sourceId: "comparison-question" },
      { type: "narration.ended" as const, sourceId: "remediation" },
      { type: "answer.correct" as const, sourceId: "comparison-question" },
      { type: "narration.ended" as const, sourceId: "slice-summary" },
    ];
    const a = replay(sampleWorkflow(), events);
    const b = replay(sampleWorkflow(), events);
    expect(a).toEqual(b);
    expect(a.finalStepId).toBe("next");
    expect(a.effects).toContainEqual({ type: "completeSlice" });
    // the remediation loop was taken, then the correct branch
    expect(a.effects).toContainEqual({ type: "playNarration", narrationId: "remediation" });
  });
});
