import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuntimeEventBus, InMemorySessionAdapter, type CourseRuntimeAdapters } from "@mind-imprint/course-runtime";
import { SlicePlayer } from "../../src/slice/SlicePlayer";
import { AudioEngineProvider } from "../../src/narration/audioEngine";
import { FakeAudioEngine } from "../support/fakeAudioEngine";
import { assessmentSlice, ASSESSMENT_PART_ID } from "../support/staticCourse";

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

async function mountSlice() {
  const { sessionAdapter, session, adapters, bus } = await setup();
  const engine = new FakeAudioEngine();
  const onSliceComplete = vi.fn();
  const onNavigateNext = vi.fn();
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
          onSliceComplete={onSliceComplete}
          onNavigateNext={onNavigateNext}
        />
      </AudioEngineProvider>,
    );
    container = r.container;
  });
  return { container, engine, onSliceComplete, onNavigateNext, sessionAdapter, session };
}

const radiogroup = (container: HTMLElement) => within(container).getByRole("radiogroup");
const radio = (container: HTMLElement, name: string) => within(container).getByRole("radio", { name }) as HTMLInputElement;
const submit = (container: HTMLElement) => within(container).getByRole("button", { name: "提交" });

describe("assessment-driven workflow branching (SlicePlayer)", () => {
  it("wrong answer enters the remediation path and re-enables the question; a later correct answer completes the slice", async () => {
    const user = userEvent.setup();
    const { container, engine, onSliceComplete, onNavigateNext } = await mountSlice();

    // intro narration plays; the question starts disabled until it ends
    expect(engine.calls.some((c) => c.op === "play" && c.url === "/resolved/audio/as-intro.mp3")).toBe(true);
    expect(radio(container, "还不能")).toBeDisabled();

    // narration.ended → wait-for-answer enables the question
    act(() => engine.fireEnded());
    expect(radio(container, "还不能")).not.toBeDisabled();

    // answer WRONG → answer.incorrect routes to remediate (disable + remediation narration)
    await user.click(radio(container, "能"));
    await user.click(submit(container));
    expect(container.querySelector('[data-narration-id="as-remediation"]')).not.toBeNull();
    expect(radio(container, "能")).toBeDisabled();
    expect(onSliceComplete).not.toHaveBeenCalled();

    // remediation narration ends → back to wait-for-answer, question re-enabled
    act(() => engine.fireEnded());
    expect(radio(container, "还不能")).not.toBeDisabled();

    // answer CORRECT → summarize narration → completes + navigates
    await user.click(radio(container, "还不能"));
    await user.click(submit(container));
    expect(container.querySelector('[data-narration-id="as-summary"]')).not.toBeNull();
    expect(onSliceComplete).not.toHaveBeenCalled();

    act(() => engine.fireEnded());
    expect(onSliceComplete).toHaveBeenCalledTimes(1);
    expect(onNavigateNext).toHaveBeenCalledTimes(1);
  });

  it("exhausting attempts routes to summarize/complete — no infinite remediation loop", async () => {
    const user = userEvent.setup();
    const { container, engine, onSliceComplete, sessionAdapter, session } = await mountSlice();

    act(() => engine.fireEnded()); // intro → enable

    // attempt 1 wrong → remediate
    await user.click(radio(container, "能"));
    await user.click(submit(container));
    expect(container.querySelector('[data-narration-id="as-remediation"]')).not.toBeNull();

    act(() => engine.fireEnded()); // remediation → re-enable

    // attempt 2 wrong = FINAL (maxAttempts:2) → attemptsExhausted → summarize (not remediate again)
    await user.click(radio(container, "能"));
    await user.click(submit(container));
    expect(container.querySelector('[data-narration-id="as-summary"]')).not.toBeNull();
    expect(container.querySelector('[data-narration-id="as-remediation"]')).toBeNull();

    act(() => engine.fireEnded()); // summary → next → complete
    expect(onSliceComplete).toHaveBeenCalledTimes(1);

    // attempt count persisted across the disable/re-enable (continuity)
    const persisted = await sessionAdapter.load(session.id);
    expect(persisted!.sliceStates[assessmentSlice.id]!.blockStates["as-question"]!.attempts).toBe(2);
    expect(persisted!.sliceStates[assessmentSlice.id]!.blockStates["as-question"]!.completed).toBe(true);
  });

  it("radiogroup is present and accessible", async () => {
    const { container } = await mountSlice();
    expect(radiogroup(container)).toBeInTheDocument();
  });

  // §Slice5 / P2-06 — `introduce-question`'s enterActions focus `as-question`.
  // Only that wrapper becomes a programmatic focus target, and its accessible
  // name is derived from the question's own `prompt` — never a raw block id.
  it("focuses as-question with a meaningful accessible name from its prompt; as-lead (not focused) carries neither", async () => {
    const { container } = await mountSlice();

    const focused = container.querySelector('[data-focus-block="as-question"]');
    expect(focused).toHaveAttribute("tabindex", "-1");
    expect(focused).toHaveAttribute("aria-label", "两个结论能直接比较吗？");

    const notFocused = container.querySelector('[data-focus-block="as-lead"]');
    expect(notFocused).not.toHaveAttribute("tabindex");
    expect(notFocused).not.toHaveAttribute("aria-label");
  });
});
