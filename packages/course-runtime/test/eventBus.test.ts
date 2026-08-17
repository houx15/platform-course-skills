import { describe, it, expect, vi } from "vitest";
import type { CourseRuntimeEvent } from "@mind-imprint/course-contract";
import { RuntimeEventBus } from "../src/eventBus";

function fixedIds(prefix: string) {
  let n = 0;
  return () => `${prefix}-${++n}`;
}

function makeBus(onDropped?: (e: CourseRuntimeEvent) => void) {
  return new RuntimeEventBus({
    courseId: "demo-course",
    sessionId: "sess-1",
    idFactory: fixedIds("evt"),
    clock: () => "2026-08-16T00:00:00.000Z",
    onDropped,
  });
}

describe("RuntimeEventBus", () => {
  it("stamps a full envelope and delivers to subscribers for the active slice", () => {
    const bus = makeBus();
    const received: CourseRuntimeEvent[] = [];
    bus.subscribe((e) => received.push(e));

    const emit = bus.bindSlice("part-1", "slice-1");
    bus.setActiveSlice("slice-1");
    emit("q1", "answer.correct", { optionId: "a" });

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({
      id: "evt-1",
      sessionId: "sess-1",
      courseId: "demo-course",
      partId: "part-1",
      sliceId: "slice-1",
      sourceId: "q1",
      type: "answer.correct",
      occurredAt: "2026-08-16T00:00:00.000Z",
      payload: { optionId: "a" },
    });
  });

  it("drops events emitted for a slice that is not active", () => {
    const dropped: CourseRuntimeEvent[] = [];
    const bus = makeBus((e) => dropped.push(e));
    const handler = vi.fn();
    bus.subscribe(handler);

    const emitStale = bus.bindSlice("part-1", "slice-1");
    bus.setActiveSlice("slice-2");
    emitStale("q1", "answer.correct");

    expect(handler).not.toHaveBeenCalled();
    expect(dropped).toHaveLength(1);
    expect(dropped[0]?.sliceId).toBe("slice-1");
  });

  it("stops delivering after unsubscribe", () => {
    const bus = makeBus();
    const handler = vi.fn();
    const off = bus.subscribe(handler);
    const emit = bus.bindSlice("part-1", "slice-1");
    bus.setActiveSlice("slice-1");

    emit("q1", "block.completed");
    off();
    emit("q1", "block.completed");

    expect(handler).toHaveBeenCalledTimes(1);
  });
});
