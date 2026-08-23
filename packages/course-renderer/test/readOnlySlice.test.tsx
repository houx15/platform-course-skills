import { act, render } from "@testing-library/react";
import { RuntimeEventBus, InMemorySessionAdapter, type CourseRuntimeAdapters } from "@mind-imprint/course-runtime";
import type { SliceDefinition } from "@mind-imprint/course-contract";
import { SlicePlayer } from "../src/slice/SlicePlayer";
import { AudioEngineProvider } from "../src/narration/audioEngine";
import { FakeAudioEngine } from "./support/fakeAudioEngine";

/**
 * A pure-READING slice: one workflow step, terminal on entry. This is how the
 * course generator authors "look at this image, read this paragraph" screens —
 * there is nothing for the student to DO, so the slice is complete the moment
 * it is entered. Live examples: course-04 slice 1, course-13 slice 1,
 * course-19 slice 1, course-23 slice 5.
 *
 * `manualNext: "after-completion"` means 下一步 stays disabled until the slice
 * reports completion, so if entering the terminal initial step does not
 * complete the slice the student is trapped with no exit at all.
 */
const READ_PART_ID = "part-read";

function readOnlySlice(): SliceDefinition {
  return {
    id: "slice-read-only",
    title: "只读片段",
    objectiveIds: ["obj-read"],
    estimatedSeconds: 30,
    blocks: [{ id: "ro-text", type: "text", content: "读完就可以继续。" }],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["ro-text"] }] },
    narrations: [],
    workflow: {
      version: "1.0",
      initialStepId: "read",
      initialState: { visibleBlockIds: ["ro-text"], enabledBlockIds: ["ro-text"] },
      steps: [{ id: "read", enterActions: [{ type: "completeSlice" }], transitions: [] }],
    },
    navigation: { previous: "allowed", manualNext: "after-completion", autoNext: false, revisit: "restore-completed-state" },
  };
}

function makeIdFactory() {
  let n = 0;
  return () => `ev-${++n}`;
}
const clock = () => "2026-08-23T00:00:00.000Z";

async function setup() {
  const sessionAdapter = new InMemorySessionAdapter({ idFactory: makeIdFactory(), clock });
  const session = await sessionAdapter.create({ courseId: "read-only-course", studentId: "student-1" });
  const adapters: CourseRuntimeAdapters = {
    assetResolver: { resolve: (p) => `/resolved/${p}` },
    sessionAdapter,
    openingGenerator: { generate: async () => ({ text: "", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true }) },
    closingGenerator: { generate: async () => ({ text: "", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true }) },
  };
  const bus = new RuntimeEventBus({ courseId: "read-only-course", sessionId: session.id, idFactory: makeIdFactory(), clock });
  return { sessionAdapter, session, adapters, bus };
}

describe("read-only slice (terminal initial step)", () => {
  it("completes on entry so 下一步 is reachable", async () => {
    const { session, adapters, bus } = await setup();
    const onSliceComplete = vi.fn();
    const onNavigateNext = vi.fn();

    await act(async () => {
      render(
        <AudioEngineProvider value={new FakeAudioEngine()}>
          <SlicePlayer
            slice={readOnlySlice()}
            partId={READ_PART_ID}
            sessionId={session.id}
            adapters={adapters}
            bus={bus}
            onSliceComplete={onSliceComplete}
            onNavigateNext={onNavigateNext}
          />
        </AudioEngineProvider>,
      );
    });

    // The whole point of the slice: entering it IS completing it.
    expect(onSliceComplete).toHaveBeenCalledTimes(1);
    // autoNext:false — completion must not drag the student forward on its own.
    expect(onNavigateNext).not.toHaveBeenCalled();
  });
});
