import { describe, it, expect } from "vitest";
import { validateCourseDefinition } from "../src/validate";
import { validCourse } from "./fixtures";

describe("validateCourseDefinition", () => {
  it("accepts the golden document", () => {
    const r = validateCourseDefinition({ schemaVersion: "2.0", course: validCourse });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.warnings).toEqual([]); // golden course has no quality warnings either
  });
  it("returns structural issues and stops when the shape is wrong", () => {
    const r = validateCourseDefinition({ schemaVersion: "2.0", course: { id: "x" } });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.issues.every((i) => i.layer === "structural")).toBe(true);
  });
  it("returns referential issues on a structurally-valid but broken course", () => {
    const broken = structuredClone(validCourse);
    broken.objectives[0]!.evidenceBlockIds = ["ghost"];
    const r = validateCourseDefinition({ schemaVersion: "2.0", course: broken });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.issues.some((i) => i.layer === "referential")).toBe(true);
  });

  // P2-09 — a WARN-only quality issue (an authoring nudge) never fails an
  // otherwise-playable course; it surfaces on the `ok: true` result instead.
  it("a WARN-only quality issue does not block ok — it surfaces in `warnings`", () => {
    const warnOnly = structuredClone(validCourse);
    (warnOnly.parts[0]!.slices[1]!.blocks[0] as any).content = "   "; // empty text: WARN only
    const r = validateCourseDefinition({ schemaVersion: "2.0", course: warnOnly });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.warnings.length).toBeGreaterThan(0);
      expect(r.warnings.every((w) => w.layer === "quality" && w.severity === "warn")).toBe(true);
    }
  });

  // A HARD quality issue (a genuine playability break) DOES block ok, same as
  // any referential/workflow issue.
  it("a HARD quality issue blocks ok, layered as 'quality'", () => {
    const hardBroken = structuredClone(validCourse);
    const question = hardBroken.parts[0]!.slices[0]!.blocks[1] as any;
    question.options[1].id = question.options[0].id; // duplicate option id: HARD
    const r = validateCourseDefinition({ schemaVersion: "2.0", course: hardBroken });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.issues.some((i) => i.layer === "quality" && i.severity !== "warn")).toBe(true);
  });
});
