import { describe, it, expect } from "vitest";
import { BlockDefinition } from "../src/blocks";

const textBlock = { id: "explain", type: "text", content: "Hello." };
const singleChoice = {
  id: "q1",
  type: "singleChoice",
  prompt: "Comparable?",
  options: [ { id: "yes", label: "Yes" }, { id: "no", label: "No" } ],
  assessment: { mode: "graded", correctOptionId: "no" },
  completion: { rule: "submit-correct-or-exhausted", maxAttempts: 3 },
};

describe("BlockDefinition", () => {
  it("parses a text block", () => {
    expect(BlockDefinition.safeParse(textBlock).success).toBe(true);
  });
  it("parses a graded single-choice block", () => {
    expect(BlockDefinition.safeParse(singleChoice).success).toBe(true);
  });
  it("rejects unknown properties (strict)", () => {
    expect(BlockDefinition.safeParse({ ...textBlock, extra: 1 }).success).toBe(false);
  });
  it("rejects an unknown block type", () => {
    expect(BlockDefinition.safeParse({ id: "x", type: "audio" }).success).toBe(false);
  });
  it("rejects a graded single-choice whose completion is submit-any-only shape mismatch", () => {
    // maxAttempts is required by submit-correct-or-exhausted
    const bad = { ...singleChoice, completion: { rule: "submit-correct-or-exhausted" } };
    expect(BlockDefinition.safeParse(bad).success).toBe(false);
  });
});
