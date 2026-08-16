import { describe, it, expect } from "vitest";
import { CourseSession, RuntimeSceneResult } from "../src/session";

describe("CourseSession", () => {
  it("parses a created session with no progress", () => {
    const s = { id: "sess-1", courseId: "demo", courseSchemaVersion: "2.0", studentId: "stu-1", status: "created", sliceStates: {}, events: [] };
    expect(CourseSession.safeParse(s).success).toBe(true);
  });
  it("rejects an unknown status", () => {
    const s = { id: "sess-1", courseId: "demo", courseSchemaVersion: "2.0", studentId: "stu-1", status: "paused", sliceStates: {}, events: [] };
    expect(CourseSession.safeParse(s).success).toBe(false);
  });
});

describe("RuntimeSceneResult", () => {
  it("parses a generated scene result", () => {
    const r = { text: "hi", generatedAt: "2026-08-16T00:00:00Z", usedSignalTypes: [], fallbackUsed: false };
    expect(RuntimeSceneResult.safeParse(r).success).toBe(true);
  });
});
