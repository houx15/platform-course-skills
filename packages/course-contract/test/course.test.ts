import { describe, it, expect } from "vitest";
import { CourseDefinitionDocument } from "../src/course";

const minimal = {
  schemaVersion: "2.0",
  course: {
    id: "demo",
    title: "Demo",
    language: "en",
    estimatedMinutes: 1,
    objectives: [ { id: "o1", text: "Learn.", evidenceBlockIds: ["q"] } ],
    opening: { learningPreview: ["a"], personalization: { enabled: false, allowedSignals: [] }, fallback: { text: "Welcome." } },
    parts: [ {
      id: "p1", title: "Part", objectiveIds: ["o1"],
      slices: [ {
        id: "s1", title: "Slice", objectiveIds: ["o1"], estimatedSeconds: 30,
        blocks: [ { id: "q", type: "text", content: "hi" } ],
        layout: { preset: "full", slots: [ { id: "main", blockIds: ["q"] } ] },
        narrations: [],
        workflow: { version: "1.0", initialStepId: "only", steps: [ { id: "only", enterActions: [ { type: "completeSlice" }, { type: "navigate", target: "nextSlice" } ], transitions: [] } ] },
        navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
      } ],
    } ],
    closing: { preparedSummary: "s", takeaways: ["t"], transferApplications: ["x"], personalization: { enabled: false, allowedSignals: [] }, fallback: { text: "Done." } },
  },
};

describe("CourseDefinitionDocument", () => {
  it("parses a minimal 2.0 course", () => {
    const r = CourseDefinitionDocument.safeParse(minimal);
    expect(r.success).toBe(true);
  });
  it("rejects a wrong schemaVersion", () => {
    expect(CourseDefinitionDocument.safeParse({ ...minimal, schemaVersion: "1.0" }).success).toBe(false);
  });
});
