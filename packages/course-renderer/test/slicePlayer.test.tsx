import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { RuntimeEventBus, InMemorySessionAdapter, type CourseRuntimeAdapters } from "@mind-imprint/course-runtime";
import { SlicePlayer } from "../src/slice/SlicePlayer";
import { AudioEngineProvider } from "../src/narration/audioEngine";
import { FakeAudioEngine } from "./support/fakeAudioEngine";
import { assessmentSlice, ASSESSMENT_PART_ID, sliceOne, STATIC_PART_ID } from "./support/staticCourse";

function makeIdFactory() {
  let n = 0;
  return () => `ev-${++n}`;
}
const clock = () => "2026-08-16T00:00:00.000Z";

function fallbackGenerator() {
  return {
    generate: async () => ({ text: "", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true }),
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
  const bus = new RuntimeEventBus({
    courseId: "static-demo-course",
    sessionId: session.id,
    idFactory: makeIdFactory(),
    clock,
  });
  return { sessionAdapter, session, adapters, bus };
}

describe("SlicePlayer", () => {
  it("drives a slice from intro narration through reveal to completion + navigation", async () => {
    const { sessionAdapter, session, adapters, bus } = await setup();
    const engine = new FakeAudioEngine();
    const onSliceComplete = vi.fn();
    const onNavigateNext = vi.fn();

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
          />
        </AudioEngineProvider>,
      );
      container = r.container;
    });

    // intro step played the narration through the engine
    expect(engine.calls.some((c) => c.op === "play" && c.url === "/resolved/audio/s1.mp3")).toBe(true);

    // the reveal block starts hidden
    const revealWrapper = () => container.querySelector('[data-block-id="s1-reveal-text"]') as HTMLElement;
    expect(revealWrapper()).toHaveAttribute("hidden");

    // narration.ended → reveal step shows the hidden block + enables continue
    act(() => engine.fireEnded());
    expect(revealWrapper()).not.toHaveAttribute("hidden");
    expect(onSliceComplete).not.toHaveBeenCalled();

    // fire the continue control through the bus → done step completes + navigates
    const emit = bus.bindSlice(STATIC_PART_ID, sliceOne.id);
    act(() => emit("s1-continue", "student.continue"));

    expect(onSliceComplete).toHaveBeenCalledTimes(1);
    expect(onNavigateNext).toHaveBeenCalledTimes(1);

    // persisted slice state reflects completion + the revealed block
    const persisted = await sessionAdapter.load(session.id);
    const sliceState = persisted!.sliceStates[sliceOne.id]!;
    expect(sliceState.status).toBe("completed");
    expect(sliceState.blockStates["s1-reveal-text"]!.visible).toBe(true);
    expect(sliceState.blockStates["s1-continue"]!.enabled).toBe(true);
  });

  it("persists every accepted event via sessionAdapter.appendEvent, with the typed payload and provenance", async () => {
    const { sessionAdapter, session, adapters, bus } = await setup();
    const appendEventSpy = vi.spyOn(sessionAdapter, "appendEvent");
    const engine = new FakeAudioEngine();

    await act(async () => {
      render(
        <AudioEngineProvider value={engine}>
          <SlicePlayer
            slice={sliceOne}
            partId={STATIC_PART_ID}
            sessionId={session.id}
            adapters={adapters}
            bus={bus}
            onSliceComplete={vi.fn()}
            onNavigateNext={vi.fn()}
          />
        </AudioEngineProvider>,
      );
    });

    act(() => engine.fireEnded()); // narration.ended → reveal
    const emit = bus.bindSlice(STATIC_PART_ID, sliceOne.id);
    act(() => emit("s1-continue", "student.continue"));

    // narration.ended (from the audio engine's mount-once subscription) and
    // student.continue both flow through the bus subscriber and get persisted.
    const persistedTypes = appendEventSpy.mock.calls.map(([, event]) => event.type);
    expect(persistedTypes).toContain("narration.ended");
    expect(persistedTypes).toContain("student.continue");

    const continueCall = appendEventSpy.mock.calls.find(([, event]) => event.type === "student.continue")!;
    expect(continueCall[0]).toBe(session.id);
    expect(continueCall[1]).toMatchObject({ sourceId: "s1-continue", type: "student.continue", sliceId: sliceOne.id });

    // Actually landed in the persisted session, not just called.
    const persisted = await sessionAdapter.load(session.id);
    expect(persisted!.events.map((e) => e.type)).toEqual(expect.arrayContaining(["narration.ended", "student.continue"]));
  });

  it("ignores events for a non-active slice (bus scoping)", async () => {
    const { adapters, bus, session } = await setup();
    const engine = new FakeAudioEngine();
    const onSliceComplete = vi.fn();
    const onNavigateNext = vi.fn();

    await act(async () => {
      render(
        <AudioEngineProvider value={engine}>
          <SlicePlayer
            slice={sliceOne}
            partId={STATIC_PART_ID}
            sessionId={session.id}
            adapters={adapters}
            bus={bus}
            onSliceComplete={onSliceComplete}
            onNavigateNext={onNavigateNext}
          />
        </AudioEngineProvider>,
      );
    });

    // an emitter bound to a DIFFERENT slice is dropped by the bus
    const strayEmit = bus.bindSlice(STATIC_PART_ID, "some-other-slice");
    act(() => strayEmit("s1-continue", "student.continue"));
    expect(onSliceComplete).not.toHaveBeenCalled();
  });

  // §Slice5 / P1-06 — a hidden block's slot wrapper stays in the DOM (never
  // removed), so revealing it later never reflows its siblings. Actual box
  // reservation is the course stylesheet's job (`.course-block[hidden]`);
  // here we prove the structural half: nothing is unmounted, and the wrapper
  // is aria-hidden while the block is not visible.
  it("a hidden block's slot wrapper is reserved (present, not removed) and aria-hidden", async () => {
    const { session, adapters, bus } = await setup();
    const engine = new FakeAudioEngine();

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
            onSliceComplete={vi.fn()}
            onNavigateNext={vi.fn()}
          />
        </AudioEngineProvider>,
      );
      container = r.container;
    });

    const wrapper = container.querySelector('[data-focus-block="s1-reveal-text"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveAttribute("aria-hidden", "true");
    expect(wrapper!.querySelector('[data-block-id="s1-reveal-text"]')).toHaveAttribute("hidden");

    // narration.ended reveals it — the SAME wrapper node reflects the change,
    // never a removed-then-remounted one (jsdom's `hidden`-toggling is what
    // caused the reflow this reservation prevents).
    act(() => engine.fireEnded());
    expect(container.querySelector('[data-focus-block="s1-reveal-text"]')).toBe(wrapper);
    expect(wrapper).not.toHaveAttribute("aria-hidden");
    expect(wrapper!.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
  });

  // Bug: after 完成本节 → 重新开始本节, an already-answered question could not be
  // re-answered and 下一步 never re-enabled. Root cause: block renderers own
  // internal UI state (an assessment's `locked`) the workflow reset never
  // touched, so a replay left the inputs disabled. The fix remounts every block
  // on replay (a per-replay React key). This drives that end-to-end.
  it("重新开始本节 remounts blocks so an answered question is answerable again", async () => {
    const { session, adapters, bus } = await setup();
    const engine = new FakeAudioEngine();

    let container!: HTMLElement;
    await act(async () => {
      const r = render(
        <AudioEngineProvider value={engine}>
          <SlicePlayer
            slice={assessmentSlice}
            partId={ASSESSMENT_PART_ID}
            sessionId={session.id}
            adapters={adapters}
            bus={bus}
            onSliceComplete={vi.fn()}
            onNavigateNext={vi.fn()}
          />
        </AudioEngineProvider>,
      );
      container = r.container;
    });

    const question = () => container.querySelector('[data-block-id="as-question"]') as HTMLElement;
    const firstRadio = () => within(question()).getAllByRole("radio")[0] as HTMLInputElement;

    // intro narration.ended → wait-for-answer enables the question.
    act(() => engine.fireEnded());
    expect(firstRadio()).toBeEnabled();

    // Answer correctly → the choice locks (inputs disabled), then summarize
    // narration.ended completes the slice.
    fireEvent.click(within(question()).getByRole("radio", { name: "还不能" }));
    fireEvent.click(within(question()).getByRole("button", { name: "提交" }));
    expect(firstRadio()).toBeDisabled(); // locked after a graded submit
    act(() => engine.fireEnded()); // as-summary ended → next → completeSlice

    // Completed → the replay control is offered.
    const replay = screen.getByRole("button", { name: "重新开始本节" });
    act(() => fireEvent.click(replay));

    // Replay restarts the workflow (question starts un-enabled again); its intro
    // narration.ended re-enables it. The remounted question must be a FRESH,
    // answerable instance — not the old locked one.
    act(() => engine.fireEnded());
    expect(firstRadio()).toBeEnabled();
    expect(firstRadio().checked).toBe(false);
    // The previous run's feedback is gone (fresh component, not the locked one).
    expect(question().querySelector("[data-single-choice-feedback]")).toBeNull();

    // And it can actually be answered again.
    fireEvent.click(within(question()).getByRole("radio", { name: "还不能" }));
    fireEvent.click(within(question()).getByRole("button", { name: "提交" }));
    expect(question().querySelector("[data-single-choice-feedback]")).not.toBeNull();
  });
});
