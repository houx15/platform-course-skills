import type { CourseSession } from "@mind-imprint/course-contract";
import { buildClosingSessionEvidence } from "../src/course/sessionEvidence";

function baseSession(overrides: Partial<CourseSession> = {}): CourseSession {
  return {
    id: "session-1",
    courseId: "demo-course",
    courseSchemaVersion: "2.0",
    studentId: "student-1",
    status: "closing",
    sliceStates: {},
    events: [],
    ...overrides,
  };
}

describe("buildClosingSessionEvidence", () => {
  it("returns an empty object when no signal is allowed, regardless of recorded state", () => {
    const session = baseSession({
      sliceStates: {
        "slice-one": {
          status: "completed",
          elapsedSeconds: 30,
          blockStates: { b1: { visible: true, enabled: true, completed: true, answer: "x", attempts: 2 } },
        },
      },
    });
    expect(buildClosingSessionEvidence(session, [])).toEqual({});
  });

  it("collects only permitted signals with recorded data, keyed by slice then block", () => {
    const session = baseSession({
      sliceStates: {
        "slice-one": {
          status: "completed",
          elapsedSeconds: 45,
          blockStates: {
            "b-answered": { visible: true, enabled: true, completed: true, answer: "not-yet", attempts: 2 },
            "b-untouched": { visible: true, enabled: false, completed: false },
          },
        },
        "slice-two": {
          status: "in-progress",
          elapsedSeconds: 0,
          blockStates: {
            "b-result": { visible: true, enabled: true, completed: true, interactionResult: { correct: true } },
          },
        },
      },
    });

    const evidence = buildClosingSessionEvidence(session, ["answers", "attempts", "time-on-slice", "interaction-results"]);

    expect(evidence).toEqual({
      answers: { "slice-one": { "b-answered": "not-yet" } },
      attempts: { "slice-one": { "b-answered": 2 } },
      "interaction-results": { "slice-two": { "b-result": { correct: true } } },
      // slice-two's elapsedSeconds is 0 (not-yet-recorded) — omitted, not sent as 0.
      "time-on-slice": { "slice-one": 45 },
    });
  });

  it("omits a permitted signal entirely when nothing was ever recorded for it, rather than sending an empty placeholder", () => {
    const session = baseSession({
      sliceStates: {
        "slice-one": {
          status: "in-progress",
          elapsedSeconds: 0,
          blockStates: { b1: { visible: true, enabled: true, completed: false } },
        },
      },
    });

    expect(buildClosingSessionEvidence(session, ["answers", "attempts", "time-on-slice", "interaction-results"])).toEqual({});
  });

  it("respects allowedSignals: a recorded fact for a NOT-permitted signal never leaks into the evidence", () => {
    const session = baseSession({
      sliceStates: {
        "slice-one": {
          status: "completed",
          elapsedSeconds: 10,
          blockStates: { b1: { visible: true, enabled: true, completed: true, answer: "secret", attempts: 3 } },
        },
      },
    });

    const evidence = buildClosingSessionEvidence(session, ["attempts"]);
    expect(evidence).toEqual({ attempts: { "slice-one": { b1: 3 } } });
    expect(evidence).not.toHaveProperty("answers");
    expect(evidence).not.toHaveProperty("time-on-slice");
  });
});
