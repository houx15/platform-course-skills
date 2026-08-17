import { act, render } from "@testing-library/react";
import { RuntimeEventBus, InMemorySessionAdapter, type CourseRuntimeAdapters } from "@mind-imprint/course-runtime";
import type { SliceDefinition } from "@mind-imprint/course-contract";
import { SlicePlayer } from "../../src/slice/SlicePlayer";
import { MediaHandleRegistry } from "../../src/media/mediaRegistry";
import { AudioEngineProvider } from "../../src/narration/audioEngine";
import { FakeAudioEngine } from "../support/fakeAudioEngine";

const PART_ID = "part-media";
const clock = () => "2026-08-16T00:00:00.000Z";
function makeIdFactory() {
  let n = 0;
  return () => `ev-${++n}`;
}
function fallbackGenerator() {
  return { generate: async () => ({ text: "", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true }) };
}

/** A minimal slice whose workflow issues one media effect on `student.continue`. */
function mediaSlice(effect: "playBlock" | "pauseBlock" | "resetBlock"): SliceDefinition {
  return {
    id: "media-slice",
    title: "媒体片段",
    objectiveIds: ["obj-one"],
    estimatedSeconds: 60,
    blocks: [{ id: "media-1", type: "text", content: "占位媒体块。" }],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["media-1"] }] },
    narrations: [],
    workflow: {
      version: "1.0",
      initialStepId: "idle",
      initialState: { visibleBlockIds: ["media-1"], enabledBlockIds: ["media-1"] },
      steps: [
        { id: "idle", enterActions: [], transitions: [{ on: { type: "student.continue" }, to: "act" }] },
        { id: "act", enterActions: [{ type: effect, targetId: "media-1" }], transitions: [] },
      ],
    },
    navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
  };
}

async function setup() {
  const sessionAdapter = new InMemorySessionAdapter({ idFactory: makeIdFactory(), clock });
  const session = await sessionAdapter.create({ courseId: "static-demo-course", studentId: "student-1" });
  const adapters: CourseRuntimeAdapters = {
    assetResolver: { resolve: (p) => `/resolved/${p}` },
    sessionAdapter,
    openingGenerator: fallbackGenerator(),
    closingGenerator: fallbackGenerator(),
  };
  const bus = new RuntimeEventBus({ courseId: "static-demo-course", sessionId: session.id, idFactory: makeIdFactory(), clock });
  return { session, adapters, bus };
}

function fakeHandle() {
  return { play: vi.fn(), pause: vi.fn(), reset: vi.fn() };
}

describe("MediaHandleRegistry", () => {
  it("register → get returns the handle; unregister removes it", () => {
    const registry = new MediaHandleRegistry();
    const handle = fakeHandle();
    const unregister = registry.register("m1", handle);
    expect(registry.get("m1")).toBe(handle);
    unregister();
    expect(registry.get("m1")).toBeUndefined();
  });

  it("a stale unregister does not evict a newer handle for the same id", () => {
    const registry = new MediaHandleRegistry();
    const first = fakeHandle();
    const second = fakeHandle();
    const unregisterFirst = registry.register("m1", first);
    registry.register("m1", second);
    unregisterFirst();
    expect(registry.get("m1")).toBe(second);
  });
});

describe("SlicePlayer media effect wiring", () => {
  async function drive(effect: "playBlock" | "pauseBlock" | "resetBlock") {
    const { session, adapters, bus } = await setup();
    const registry = new MediaHandleRegistry();
    const handle = fakeHandle();
    registry.register("media-1", handle);

    await act(async () => {
      render(
        <AudioEngineProvider value={new FakeAudioEngine()}>
          <SlicePlayer
            slice={mediaSlice(effect)}
            partId={PART_ID}
            sessionId={session.id}
            adapters={adapters}
            bus={bus}
            mediaRegistry={registry}
            onSliceComplete={vi.fn()}
            onNavigateNext={vi.fn()}
          />
        </AudioEngineProvider>,
      );
    });

    const emit = bus.bindSlice(PART_ID, "media-slice");
    act(() => emit("media-1", "student.continue"));
    return handle;
  }

  it("playBlock effect calls the registered handle's play", async () => {
    const handle = await drive("playBlock");
    expect(handle.play).toHaveBeenCalledTimes(1);
    expect(handle.pause).not.toHaveBeenCalled();
    expect(handle.reset).not.toHaveBeenCalled();
  });

  it("pauseBlock effect calls the registered handle's pause", async () => {
    const handle = await drive("pauseBlock");
    expect(handle.pause).toHaveBeenCalledTimes(1);
    expect(handle.play).not.toHaveBeenCalled();
  });

  it("resetBlock effect calls the registered handle's reset", async () => {
    const handle = await drive("resetBlock");
    expect(handle.reset).toHaveBeenCalledTimes(1);
  });
});
