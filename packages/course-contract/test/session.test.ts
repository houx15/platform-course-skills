import { describe, it, expect } from "vitest";
import { CourseSession, RuntimeSceneResult, isCourseSessionStale } from "../src/session";

describe("CourseSession", () => {
  it("parses a created session with no progress", () => {
    const s = { id: "sess-1", courseId: "demo", courseSchemaVersion: "2.0", studentId: "stu-1", status: "created", sliceStates: {}, events: [] };
    expect(CourseSession.safeParse(s).success).toBe(true);
  });
  it("rejects an unknown status", () => {
    const s = { id: "sess-1", courseId: "demo", courseSchemaVersion: "2.0", studentId: "stu-1", status: "paused", sliceStates: {}, events: [] };
    expect(CourseSession.safeParse(s).success).toBe(false);
  });

  // D5 / P2-08 — courseDefinitionHash is optional so a session persisted
  // BEFORE this field existed still parses (back-compat).
  it("parses a session with NO courseDefinitionHash (a pre-existing session)", () => {
    const s = { id: "sess-1", courseId: "demo", courseSchemaVersion: "2.0", studentId: "stu-1", status: "created", sliceStates: {}, events: [] };
    const r = CourseSession.safeParse(s);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.courseDefinitionHash).toBeUndefined();
  });
  it("parses a session WITH a courseDefinitionHash", () => {
    const s = {
      id: "sess-1",
      courseId: "demo",
      courseSchemaVersion: "2.0",
      studentId: "stu-1",
      status: "created",
      sliceStates: {},
      events: [],
      courseDefinitionHash: "abc123",
    };
    const r = CourseSession.safeParse(s);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.courseDefinitionHash).toBe("abc123");
  });
});

describe("RuntimeSceneResult", () => {
  it("parses a generated scene result", () => {
    const r = { text: "hi", generatedAt: "2026-08-16T00:00:00Z", usedSignalTypes: [], fallbackUsed: false };
    expect(RuntimeSceneResult.safeParse(r).success).toBe(true);
  });
});

// D5 / P2-08 — the pure comparison helper the definition-revision policy is
// built on. The real sha256 is Go's job (course_definition.go); this is just
// deterministic string comparison with a safe back-compat default.
describe("isCourseSessionStale", () => {
  it("is NOT stale when the session has no recorded hash (pre-existing/brand-new session) — safe back-compat default", () => {
    expect(isCourseSessionStale({ courseDefinitionHash: undefined }, "hash-b")).toBe(false);
  });
  it("is NOT stale when the recorded hash matches the current hash", () => {
    expect(isCourseSessionStale({ courseDefinitionHash: "hash-a" }, "hash-a")).toBe(false);
  });
  it("IS stale when the recorded hash disagrees with the current hash", () => {
    expect(isCourseSessionStale({ courseDefinitionHash: "hash-a" }, "hash-b")).toBe(true);
  });
});
