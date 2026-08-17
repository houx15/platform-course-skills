import { describe, it, expect } from "vitest";
import type { CourseRuntimeEvent, RuntimeSceneResult } from "@mind-imprint/course-contract";
import { InMemorySessionAdapter } from "../src/adapters";

function fixedIds(prefix: string) {
  let n = 0;
  return () => `${prefix}-${++n}`;
}

describe("InMemorySessionAdapter", () => {
  it("creates, appends events, persists status and scenes, and loads back", async () => {
    const adapter = new InMemorySessionAdapter({
      idFactory: fixedIds("sess"),
      clock: () => "2026-08-16T00:00:00.000Z",
    });

    const created = await adapter.create({ courseId: "demo-course", studentId: "student-a" });
    expect(created.id).toBe("sess-1");
    expect(created.status).toBe("created");
    expect(created.courseSchemaVersion).toBe("2.0");
    expect(created.sliceStates).toEqual({});
    expect(created.events).toEqual([]);

    const event: CourseRuntimeEvent = {
      id: "evt-1",
      sessionId: created.id,
      courseId: "demo-course",
      partId: "part-1",
      sliceId: "slice-1",
      sourceId: "q1",
      type: "answer.correct",
      occurredAt: "2026-08-16T00:00:01.000Z",
      payload: { optionId: "a" },
    };
    await adapter.appendEvent(created.id, event);

    await adapter.setStatus(created.id, "in-progress");
    await adapter.saveSliceState(created.id, "slice-1", {
      status: "in-progress",
      elapsedSeconds: 0,
      blockStates: {},
    });

    const scene: RuntimeSceneResult = {
      text: "welcome",
      generatedAt: "2026-08-16T00:00:00.000Z",
      usedSignalTypes: [],
      fallbackUsed: true,
    };
    await adapter.saveScene(created.id, "opening", scene);
    // D5 / P2-08 — the content-hash setter mirrors setStatus/setCurrent.
    await adapter.setDefinitionHash(created.id, "def-hash-1");

    const loaded = await adapter.load(created.id);
    expect(loaded).not.toBeNull();
    expect(loaded!.events).toHaveLength(1);
    expect(loaded!.events[0]).toEqual(event);
    expect(loaded!.status).toBe("in-progress");
    expect(loaded!.sliceStates["slice-1"]?.status).toBe("in-progress");
    expect(loaded!.opening).toEqual(scene);
    expect(loaded!.courseDefinitionHash).toBe("def-hash-1");

    expect(await adapter.load("nope")).toBeNull();
  });

  // D5 / P2-08 durability — CoursePlayer's stale-hash reset must clear the
  // PERSISTED progress, not merely the renderer's in-memory cache, or a
  // later resume (once the stamped hash matches) resurrects it.
  it("resetProgress() clears `current` and `sliceStates` but leaves status/hash/events untouched", async () => {
    const adapter = new InMemorySessionAdapter({
      idFactory: fixedIds("sess"),
      clock: () => "2026-08-16T00:00:00.000Z",
    });
    const created = await adapter.create({ courseId: "demo-course", studentId: "student-a" });
    await adapter.setStatus(created.id, "in-progress");
    await adapter.setCurrent(created.id, { partId: "part-1", sliceId: "slice-1", workflowStepId: "step-1" });
    await adapter.saveSliceState(created.id, "slice-1", { status: "in-progress", elapsedSeconds: 3, blockStates: {} });
    await adapter.setDefinitionHash(created.id, "old-hash");

    await adapter.resetProgress(created.id);

    const loaded = await adapter.load(created.id);
    expect(loaded!.current).toBeUndefined();
    expect(loaded!.sliceStates).toEqual({});
    // Untouched by resetProgress — CoursePlayer stamps the new hash and
    // status separately.
    expect(loaded!.status).toBe("in-progress");
    expect(loaded!.courseDefinitionHash).toBe("old-hash");
  });

  it("returns isolated copies so callers cannot mutate stored state", async () => {
    const adapter = new InMemorySessionAdapter({
      idFactory: fixedIds("sess"),
      clock: () => "2026-08-16T00:00:00.000Z",
    });
    const created = await adapter.create({ courseId: "demo-course", studentId: "student-a" });
    created.events.push({
      id: "evt-x",
      sessionId: created.id,
      courseId: "demo-course",
      sourceId: "s",
      type: "block.completed",
      occurredAt: "2026-08-16T00:00:02.000Z",
      payload: null,
    });
    const loaded = await adapter.load(created.id);
    expect(loaded!.events).toHaveLength(0);
  });
});
