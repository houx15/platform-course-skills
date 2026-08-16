import { describe, it, expect } from "vitest";
import { CourseDefinitionDocument } from "../src/course";
import { validateReferential } from "../src/validate/referential";
import { validateSliceWorkflow } from "../src/validate/workflow";
import { validCourse } from "./fixtures";

describe("golden coverage course", () => {
  it("is structurally valid", () => {
    expect(CourseDefinitionDocument.safeParse({ schemaVersion: "2.0", course: validCourse }).success).toBe(true);
  });
  it("is referentially clean", () => {
    expect(validateReferential(validCourse)).toEqual([]);
  });
  it("has clean workflows on every slice", () => {
    for (const part of validCourse.parts) for (const slice of part.slices) {
      expect(validateSliceWorkflow(slice, slice.id)).toEqual([]);
    }
  });
  it("exercises every block type", () => {
    const types = new Set(validCourse.parts.flatMap((p) => p.slices.flatMap((s) => s.blocks.map((b) => b.type))));
    for (const t of ["text","images","pdf","video","interactiveHtml","fillBlank","singleChoice"]) expect(types.has(t as any)).toBe(true);
  });
  it("exercises every layout preset", () => {
    const presets = new Set(validCourse.parts.flatMap((p) => p.slices.map((s) => s.layout.preset)));
    for (const p of ["full","split-horizontal","split-vertical","grid"]) expect(presets.has(p as any)).toBe(true);
  });
});
