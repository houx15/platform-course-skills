import { PROTOCOL_NAME, PROTOCOL_VERSION, parseFrameMessage } from "../../src/blocks/html/protocol";

const ctx = { sessionToken: "tok-123", expectedVersion: "1.0" as const };

function msg(overrides: Record<string, unknown> = {}) {
  return {
    protocol: PROTOCOL_NAME,
    version: PROTOCOL_VERSION,
    sessionToken: "tok-123",
    type: "completed",
    payload: { correct: true, value: 1 },
    ...overrides,
  };
}

/** A valid payload per type, so type-sweeping tests don't accidentally exercise the "payload" rejection. */
const VALID_PAYLOAD_FOR: Record<string, unknown> = {
  ready: { step: 0 },
  progress: { step: 1 },
  completed: { correct: true, value: 1 },
  error: { message: "boom" },
};

describe("parseFrameMessage", () => {
  it("exposes the frozen protocol identity", () => {
    expect(PROTOCOL_NAME).toBe("mind-course-interaction");
    expect(PROTOCOL_VERSION).toBe("1.0");
  });

  it("accepts a well-formed completed message with the right token/version", () => {
    const r = parseFrameMessage(msg(), ctx);
    expect(r).toEqual({ ok: true, type: "completed", payload: { correct: true, value: 1 } });
  });

  it("accepts each known type (ready/progress/completed/error) with a type-appropriate payload", () => {
    for (const type of ["ready", "progress", "completed", "error"]) {
      const r = parseFrameMessage(msg({ type, payload: VALID_PAYLOAD_FOR[type] }), ctx);
      expect(r.ok).toBe(true);
      if (r.ok) expect(r.type).toBe(type);
    }
  });

  it("rejects a wrong session token with reason 'token'", () => {
    expect(parseFrameMessage(msg({ sessionToken: "nope" }), ctx)).toEqual({ ok: false, reason: "token" });
  });

  it("rejects a wrong protocol version with reason 'version'", () => {
    expect(parseFrameMessage(msg({ version: "2.0" }), ctx)).toEqual({ ok: false, reason: "version" });
  });

  it("rejects an unknown type with reason 'type'", () => {
    expect(parseFrameMessage(msg({ type: "explode" }), ctx)).toEqual({ ok: false, reason: "type" });
  });

  it("rejects a non-object with reason 'shape'", () => {
    expect(parseFrameMessage(null, ctx)).toEqual({ ok: false, reason: "shape" });
    expect(parseFrameMessage("completed", ctx)).toEqual({ ok: false, reason: "shape" });
    expect(parseFrameMessage(42, ctx)).toEqual({ ok: false, reason: "shape" });
  });

  it("rejects a message with a missing/mismatched protocol name with reason 'shape'", () => {
    expect(parseFrameMessage(msg({ protocol: undefined }), ctx)).toEqual({ ok: false, reason: "shape" });
    expect(parseFrameMessage(msg({ protocol: "other-app" }), ctx)).toEqual({ ok: false, reason: "shape" });
  });

  it("carries a type-appropriate payload through validated (may be absent for ready)", () => {
    const r = parseFrameMessage(msg({ type: "ready", payload: undefined }), ctx);
    expect(r).toEqual({ ok: true, type: "ready", payload: undefined });
  });

  describe("payload validation (P1-08)", () => {
    it("rejects a 'completed' message with no learning evidence, reason 'payload'", () => {
      expect(parseFrameMessage(msg({ payload: {} }), ctx)).toEqual({ ok: false, reason: "payload" });
    });

    it("rejects a 'completed' message with an unknown extra field (strict), reason 'payload'", () => {
      expect(parseFrameMessage(msg({ payload: { correct: true, score: 5 } }), ctx)).toEqual({ ok: false, reason: "payload" });
    });

    it("accepts a 'completed' message with only 'value' evidence (no 'correct')", () => {
      const r = parseFrameMessage(msg({ payload: { value: { answers: ["a", "b"] } } }), ctx);
      expect(r).toEqual({ ok: true, type: "completed", payload: { value: { answers: ["a", "b"] } } });
    });

    it("accepts a 'completed' message carrying the frame's own resultId alongside evidence", () => {
      const r = parseFrameMessage(msg({ payload: { resultId: "attempt-1", correct: false, value: "x" } }), ctx);
      expect(r).toEqual({ ok: true, type: "completed", payload: { resultId: "attempt-1", correct: false, value: "x" } });
    });

    it("rejects an 'error' message missing the required 'message' field, reason 'payload'", () => {
      expect(parseFrameMessage(msg({ type: "error", payload: { code: "x" } }), ctx)).toEqual({ ok: false, reason: "payload" });
    });

    it("accepts a 'ready'/'progress' message with an empty or arbitrary informational payload", () => {
      expect(parseFrameMessage(msg({ type: "ready", payload: {} }), ctx)).toEqual({ ok: true, type: "ready", payload: {} });
      expect(parseFrameMessage(msg({ type: "progress", payload: { step: 2, total: 5 } }), ctx)).toEqual({
        ok: true,
        type: "progress",
        payload: { step: 2, total: 5 },
      });
    });
  });
});
