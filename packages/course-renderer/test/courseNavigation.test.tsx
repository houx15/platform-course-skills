import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { SliceDefinition } from "@mind-imprint/course-contract";
import { InMemorySessionAdapter, RuntimeEventBus, type CourseRuntimeAdapters } from "@mind-imprint/course-runtime";
import { SlicePlayer } from "../src/slice/SlicePlayer";
import { AudioEngineProvider } from "../src/narration/audioEngine";
import { FakeAudioEngine } from "./support/fakeAudioEngine";
import { sliceOne, STATIC_PART_ID } from "./support/staticCourse";

function makeIdFactory() {
  let n = 0;
  return () => `ev-${++n}`;
}
const clock = () => "2026-08-16T00:00:00.000Z";

function fallbackGenerator() {
  return { generate: async () => ({ text: "", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true }) };
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
  return { sessionAdapter, session, adapters, bus };
}

/**
 * A minimal, narration-free Slice whose completing step ("done") does
 * `completeSlice` with NO paired `navigate` effect — the exact §Slice4/P1-05
 * scenario a workflow must never get stuck in: the ONLY way it advances is
 * through the renderer's own manualNext/autoNext policy, never a workflow
 * effect. `wait` transitions on `student.continue`, giving the P1-05 producer
 * something real to drive.
 */
function gatedSlice(navigation: SliceDefinition["navigation"]): SliceDefinition {
  return {
    id: "gated-slice",
    title: "受控完成",
    objectiveIds: ["obj-one"],
    estimatedSeconds: 30,
    blocks: [{ id: "g-text", type: "text", content: "完成此节。" }],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["g-text"] }] },
    narrations: [],
    workflow: {
      version: "1.0",
      initialStepId: "wait",
      steps: [
        { id: "wait", enterActions: [], transitions: [{ on: { type: "student.continue" }, to: "done" }] },
        { id: "done", enterActions: [{ type: "completeSlice" }], transitions: [] },
      ],
    },
    navigation,
  };
}

describe("Course navigation (§Slice4 / P1-05)", () => {
  it('manualNext:"after-completion" — 下一步 stays disabled until the Slice completes, then advances on click', async () => {
    const { session, adapters, bus } = await setup();
    const onNavigateNext = vi.fn();
    render(
      <SlicePlayer
        slice={gatedSlice({ previous: "allowed", manualNext: "after-completion", autoNext: false, revisit: "restore-completed-state" })}
        partId={STATIC_PART_ID}
        sessionId={session.id}
        adapters={adapters}
        bus={bus}
        onSliceComplete={vi.fn()}
        onNavigateNext={onNavigateNext}
      />,
    );

    expect(screen.getByRole("button", { name: "下一步" })).toBeDisabled();

    // The P1-05 producer: the workflow's `wait` step is genuinely waiting on
    // `student.continue`, so the control is visible and, once used, completes it.
    expect(screen.getByRole("button", { name: "继续" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "继续" }));

    expect(onNavigateNext).not.toHaveBeenCalled(); // autoNext:false — no click yet, must not be stuck OR auto-skip
    expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "下一步" }));
    expect(onNavigateNext).toHaveBeenCalledTimes(1);
  });

  it('manualNext:"allowed" — 下一步 is always enabled, even before completion, and advancing does not require completion', async () => {
    const { session, adapters, bus } = await setup();
    const onNavigateNext = vi.fn();
    render(
      <SlicePlayer
        slice={gatedSlice({ previous: "allowed", manualNext: "allowed", autoNext: false, revisit: "restore-completed-state" })}
        partId={STATIC_PART_ID}
        sessionId={session.id}
        adapters={adapters}
        bus={bus}
        onSliceComplete={vi.fn()}
        onNavigateNext={onNavigateNext}
      />,
    );

    expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "下一步" }));
    expect(onNavigateNext).toHaveBeenCalledTimes(1);
  });

  it("autoNext:true — a Slice that completes WITHOUT an explicit workflow `navigate` advances on its own, no click needed", async () => {
    const { session, adapters, bus } = await setup();
    const onNavigateNext = vi.fn();
    const onSliceComplete = vi.fn();
    render(
      <SlicePlayer
        slice={gatedSlice({ previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" })}
        partId={STATIC_PART_ID}
        sessionId={session.id}
        adapters={adapters}
        bus={bus}
        onSliceComplete={onSliceComplete}
        onNavigateNext={onNavigateNext}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(onSliceComplete).toHaveBeenCalledTimes(1);
    // No click on 下一步 at all — completion alone drove the advance.
    expect(onNavigateNext).toHaveBeenCalledTimes(1);
  });

  it("上一步 is omitted (not merely disabled) when the host supplies no onNavigatePrevious", async () => {
    const { session, adapters, bus } = await setup();
    render(
      <SlicePlayer
        slice={gatedSlice({ previous: "allowed", manualNext: "allowed", autoNext: false, revisit: "restore-completed-state" })}
        partId={STATIC_PART_ID}
        sessionId={session.id}
        adapters={adapters}
        bus={bus}
        onSliceComplete={vi.fn()}
        onNavigateNext={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "上一步" })).toBeDisabled();
  });

  it("上一步 fires the host callback when supplied", async () => {
    const { session, adapters, bus } = await setup();
    const onNavigatePrevious = vi.fn();
    render(
      <SlicePlayer
        slice={gatedSlice({ previous: "allowed", manualNext: "allowed", autoNext: false, revisit: "restore-completed-state" })}
        partId={STATIC_PART_ID}
        sessionId={session.id}
        adapters={adapters}
        bus={bus}
        onSliceComplete={vi.fn()}
        onNavigateNext={vi.fn()}
        onNavigatePrevious={onNavigatePrevious}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "上一步" }));
    expect(onNavigatePrevious).toHaveBeenCalledTimes(1);
  });

  it("继续 (student.continue producer) is absent once nothing is waiting on it — e.g. the terminal step", async () => {
    const { session, adapters, bus } = await setup();
    render(
      <SlicePlayer
        slice={gatedSlice({ previous: "allowed", manualNext: "after-completion", autoNext: false, revisit: "restore-completed-state" })}
        partId={STATIC_PART_ID}
        sessionId={session.id}
        adapters={adapters}
        bus={bus}
        onSliceComplete={vi.fn()}
        onNavigateNext={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "继续" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "继续" }));
    // "done" has no transitions at all — nothing waits on student.continue anymore.
    expect(screen.queryByRole("button", { name: "继续" })).toBeNull();
  });

  it("revisit — mounting directly into an already-completed step shows it completed WITHOUT re-firing completeSlice/navigate/narration, and offers an explicit replay that re-runs from initial", async () => {
    const { session, adapters, bus } = await setup();
    const engine = new FakeAudioEngine();
    const onSliceComplete = vi.fn();
    const onNavigateNext = vi.fn();

    const completedState = {
      status: "completed" as const,
      currentWorkflowStepId: "done",
      startedAt: clock(),
      completedAt: clock(),
      elapsedSeconds: 5,
      blockStates: {
        "s1-intro-text": { visible: true, enabled: true, completed: false },
        "s1-reveal-text": { visible: true, enabled: true, completed: false },
        "s1-continue": { visible: true, enabled: true, completed: false },
      },
    };

    let container!: HTMLElement;
    await act(async () => {
      const r = render(
        <AudioEngineProvider value={engine}>
          <SlicePlayer
            slice={sliceOne}
            partId={STATIC_PART_ID}
            sessionId={session.id}
            adapters={adapters}
            bus={bus}
            onSliceComplete={onSliceComplete}
            onNavigateNext={onNavigateNext}
            restoreStepId="done"
            restoreState={completedState}
          />
        </AudioEngineProvider>,
      );
      container = r.container;
    });

    // Landed on "done" (terminal: completeSlice + navigate) WITHOUT re-firing
    // either effect — the dangerous case this guard exists for.
    expect(onSliceComplete).not.toHaveBeenCalled();
    expect(onNavigateNext).not.toHaveBeenCalled();
    expect(engine.calls.some((c) => c.op === "play")).toBe(false);
    // Shown completed, not frozen mid-slice: the reveal block is visible per
    // the restored state, and an explicit replay path is offered.
    expect(container.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    expect(screen.getByRole("button", { name: "重新开始本节" })).toBeInTheDocument();

    // Replay re-runs the workflow from `initialStepId`: the reveal block hides
    // again (intro's initialState) and the intro narration genuinely replays.
    await userEvent.click(screen.getByRole("button", { name: "重新开始本节" }));
    expect(container.querySelector('[data-block-id="s1-reveal-text"]')).toHaveAttribute("hidden");
    expect(engine.calls.some((c) => c.op === "play" && c.url === "/resolved/audio/s1.mp3")).toBe(true);

    // The replayed run is genuinely live — narration.ended now drives it forward.
    act(() => engine.fireEnded());
    expect(container.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
  });
});
