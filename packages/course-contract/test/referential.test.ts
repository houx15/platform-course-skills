import { describe, it, expect } from "vitest";
import { validateReferential } from "../src/validate/referential";
import { validCourse } from "./fixtures";

const clone = () => structuredClone(validCourse);
const messages = (issues: { message: string }[]) => issues.map((i) => i.message).join(" | ");

describe("validateReferential", () => {
  it("passes on the golden course", () => {
    expect(validateReferential(validCourse)).toEqual([]);
  });
  it("flags a duplicate block id across slices", () => {
    const c = clone();
    c.parts[0]!.slices[0]!.blocks[0]!.id = "dup";
    c.parts[0]!.slices[1]!.blocks[0]!.id = "dup"; // fixture must have ≥2 slices
    expect(messages(validateReferential(c))).toMatch(/duplicate block id/i);
  });
  it("flags a block not assigned to any slot", () => {
    const c = clone();
    c.parts[0]!.slices[0]!.layout.slots[0]!.blockIds = [];
    expect(messages(validateReferential(c))).toMatch(/not assigned to a slot/i);
  });
  it("flags a slot referencing a non-existent block", () => {
    const c = clone();
    c.parts[0]!.slices[0]!.layout.slots[0]!.blockIds.push("ghost");
    expect(messages(validateReferential(c))).toMatch(/unknown block/i);
  });
  it("flags an objective whose evidence block does not exist", () => {
    const c = clone();
    c.objectives[0]!.evidenceBlockIds = ["nope"];
    expect(messages(validateReferential(c))).toMatch(/evidence block/i);
  });
  it("flags a graded single-choice whose correctOptionId is not an option", () => {
    const c = clone();
    const sc = c.parts[0]!.slices[0]!.blocks.find((b: any) => b.type === "singleChoice") as any;
    sc.assessment.correctOptionId = "missing";
    expect(messages(validateReferential(c))).toMatch(/correctOptionId/i);
  });
});
