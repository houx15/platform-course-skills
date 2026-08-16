import { describe, it, expect } from "vitest";
import { validateCourseDefinition } from "../src/validate";
import { validCourse } from "./fixtures";

describe("validateCourseDefinition", () => {
  it("accepts the golden document", () => {
    const r = validateCourseDefinition({ schemaVersion: "2.0", course: validCourse });
    expect(r.ok).toBe(true);
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
});
