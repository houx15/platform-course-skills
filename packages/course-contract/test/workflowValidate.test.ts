import { describe, it, expect } from "vitest";
import { validateSliceWorkflow } from "../src/validate/workflow";
import { validCourse } from "./fixtures";

const golden = () => structuredClone(validCourse.parts[0]!.slices[0]!);
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
