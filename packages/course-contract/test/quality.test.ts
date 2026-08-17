import { describe, it, expect } from "vitest";
import { validateQuality } from "../src/validate/quality";
import type { CourseDefinitionDocument } from "../src/course";
import type { ValidationIssue } from "../src/validate/types";
import { validCourse } from "./fixtures";

const doc = (): CourseDefinitionDocument => ({ schemaVersion: "2.0", course: structuredClone(validCourse) });
const messages = (issues: ValidationIssue[]) => issues.map((i) => i.message).join(" | ");
const errors = (issues: ValidationIssue[]) => issues.filter((i) => i.severity !== "warn");
const warnings = (issues: ValidationIssue[]) => issues.filter((i) => i.severity === "warn");

describe("validateQuality — P2-09 contract-quality checks", () => {
  it("passes clean on the golden course: no hard issues, no warnings", () => {
    expect(validateQuality(doc())).toEqual([]);
  });

  // --- HARD: image item id uniqueness ---
  it("(HARD) flags a duplicate image item id within one images block", () => {
    const d = doc();
    const images = d.course.parts[0]!.slices[2]!.blocks[0] as any;
    expect(images.type).toBe("images");
    images.items[1].id = images.items[0].id;
    const issues = validateQuality(d);
    expect(errors(issues).length).toBeGreaterThan(0);
    expect(messages(errors(issues))).toMatch(/duplicate image item id/i);
    expect(errors(issues).every((i) => i.layer === "quality")).toBe(true);
  });

  // --- HARD: presentation:"single" must have exactly one item ---
  it("(HARD) flags a presentation:\"single\" images block with more than one item", () => {
    const d = doc();
    const images = d.course.parts[0]!.slices[2]!.blocks[0] as any;
    images.presentation = "single";
    expect(images.items.length).toBeGreaterThan(1);
    const issues = validateQuality(d);
    expect(messages(errors(issues))).toMatch(/presentation:"single".*items/i);
  });

  it("(HARD, positive) presentation:\"single\" with exactly one item passes clean", () => {
    const d = doc();
    const images = d.course.parts[0]!.slices[2]!.blocks[0] as any;
    images.presentation = "single";
    images.items = [images.items[0]];
    // Re-point the sim slice's layout isn't touched; only the item count matters here.
    expect(validateQuality(d).filter((i) => i.message.includes("presentation"))).toEqual([]);
  });

  // --- HARD: singleChoice option id uniqueness ---
  it("(HARD) flags a duplicate singleChoice option id within one block", () => {
    const d = doc();
    const question = d.course.parts[0]!.slices[0]!.blocks[1] as any;
    expect(question.type).toBe("singleChoice");
    question.options[1].id = question.options[0].id;
    const issues = validateQuality(d);
    expect(messages(errors(issues))).toMatch(/duplicate option id/i);
  });

  // --- HARD: the server's 256-asset cap ---
  it("(HARD) flags a course whose asset paths exceed the 256-asset cap", () => {
    const items = Array.from({ length: 257 }, (_, i) => ({ id: `img-${i}`, source: `assets/images/${i}.png`, alt: `图 ${i}` }));
    const bigDoc: CourseDefinitionDocument = {
      schemaVersion: "2.0",
      course: {
        id: "big-course",
        title: "Asset Cap Test",
        language: "en",
        estimatedMinutes: 5,
        objectives: [{ id: "o1", text: "x", evidenceBlockIds: ["gallery"] }],
        opening: { learningPreview: [], personalization: { enabled: false, allowedSignals: [] }, fallback: { text: "hi" } },
        closing: {
          preparedSummary: "s",
          takeaways: [],
          transferApplications: [],
          personalization: { enabled: false, allowedSignals: [] },
          fallback: { text: "bye" },
        },
        parts: [
          {
            id: "p1",
            title: "P",
            objectiveIds: ["o1"],
            slices: [
              {
                id: "s1",
                title: "S",
                objectiveIds: ["o1"],
                estimatedSeconds: 60,
                narrations: [],
                blocks: [{ id: "gallery", type: "images", presentation: "gallery", items }],
                layout: {} as never,
                workflow: {} as never,
                navigation: {} as never,
              },
            ],
          },
        ],
      },
    } as unknown as CourseDefinitionDocument;
    const issues = validateQuality(bigDoc);
    expect(messages(errors(issues))).toMatch(/257 assets, exceeding the server's 256-asset cap/i);
  });

  it("(HARD, positive) a course with exactly 256 assets does not trip the cap", () => {
    const items = Array.from({ length: 256 }, (_, i) => ({ id: `img-${i}`, source: `assets/images/${i}.png`, alt: `图 ${i}` }));
    const okDoc = {
      schemaVersion: "2.0",
      course: {
        id: "ok-course",
        title: "Asset Cap Test",
        language: "en",
        estimatedMinutes: 5,
        objectives: [{ id: "o1", text: "x", evidenceBlockIds: ["gallery"] }],
        opening: { learningPreview: [], personalization: { enabled: false, allowedSignals: [] }, fallback: { text: "hi" } },
        closing: {
          preparedSummary: "s",
          takeaways: [],
          transferApplications: [],
          personalization: { enabled: false, allowedSignals: [] },
          fallback: { text: "bye" },
        },
        parts: [
          {
            id: "p1",
            title: "P",
            objectiveIds: ["o1"],
            slices: [
              {
                id: "s1",
                title: "S",
                objectiveIds: ["o1"],
                estimatedSeconds: 60,
                narrations: [],
                blocks: [{ id: "gallery", type: "images", presentation: "gallery", items }],
                layout: {} as never,
                workflow: {} as never,
                navigation: {} as never,
              },
            ],
          },
        ],
      },
    } as unknown as CourseDefinitionDocument;
    expect(validateQuality(okDoc).filter((i) => i.message.includes("asset cap"))).toEqual([]);
  });

  // --- WARN: empty text content ---
  it("(WARN) flags an empty text block, non-blocking", () => {
    const d = doc();
    const text = d.course.parts[0]!.slices[1]!.blocks[0] as any;
    expect(text.type).toBe("text");
    text.content = "   ";
    const issues = validateQuality(d);
    expect(errors(issues)).toEqual([]); // never hard
    expect(messages(warnings(issues))).toMatch(/empty content/i);
    expect(warnings(issues)[0]!.severity).toBe("warn");
    expect(warnings(issues)[0]!.layer).toBe("quality");
  });

  // --- WARN: estimatedMinutes vs. slice totals ---
  it("(WARN) flags a large estimatedMinutes/slice-total mismatch, non-blocking", () => {
    const d = doc();
    d.course.estimatedMinutes = 1; // slices total 450s = 7.5min, way off 1min
    const issues = validateQuality(d);
    expect(errors(issues)).toEqual([]);
    expect(messages(warnings(issues))).toMatch(/estimatedMinutes/i);
  });

  it("(WARN, positive) a close estimatedMinutes/slice-total match does not warn", () => {
    // golden: estimatedMinutes=6 (360s) vs. slices totalling 450s — within tolerance.
    expect(validateQuality(doc()).filter((i) => i.message.includes("estimatedMinutes"))).toEqual([]);
  });

  // --- WARN: evidenceBlockIds pointing at non-evidence-producing blocks ---
  it("(WARN) flags an objective's evidenceBlockIds pointing at a static text/image/pdf block, non-blocking", () => {
    const d = doc();
    d.course.objectives[0]!.evidenceBlockIds = ["intro-text"]; // a `text` block
    const issues = validateQuality(d);
    expect(errors(issues)).toEqual([]);
    expect(messages(warnings(issues))).toMatch(/produces no learner evidence/i);
  });

  it("(WARN, positive) evidenceBlockIds pointing at singleChoice/fillBlank/video/interactiveHtml blocks never warn", () => {
    // golden: check-comparability -> comparison-question (singleChoice) + evidence-reflection (fillBlank).
    expect(validateQuality(doc()).filter((i) => i.message.includes("produces no learner evidence"))).toEqual([]);
  });

  it("does not flag an evidence id that doesn't exist at all — that's validateReferential's job", () => {
    const d = doc();
    d.course.objectives[0]!.evidenceBlockIds = ["ghost-block"];
    // validateQuality only judges ids that DO resolve; an unknown id produces
    // no quality issue (referential.ts's existence check owns that case).
    expect(validateQuality(d)).toEqual([]);
  });
});
