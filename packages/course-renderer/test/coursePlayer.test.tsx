import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CourseSession, SliceSessionState } from "@mind-imprint/course-contract";
import {
  InMemorySessionAdapter,
  type CourseRuntimeAdapters,
  type RuntimeEventBus,
  type RuntimeSceneGenerator,
  type SceneGenerationInput,
  type SessionAdapter,
} from "@mind-imprint/course-runtime";
import { CoursePlayer } from "../src/course/CoursePlayer";
import { AudioEngineProvider } from "../src/narration/audioEngine";
import { FakeAudioEngine } from "./support/fakeAudioEngine";
import { staticCourseDocument } from "./support/staticCourse";

function makeIdFactory(prefix: string) {
  let n = 0;
  return () => `${prefix}-${++n}`;
}
const clock = () => "2026-08-16T00:00:00.000Z";

/** Fallback generator: echoes the input fallback text, flagged fallbackUsed. */
const fallbackGenerator: RuntimeSceneGenerator = {
  generate: async (input: SceneGenerationInput) => ({
    text: input.fallback.text,
    audioUrl: input.fallback.audioUrl,
    generatedAt: clock(),
    usedSignalTypes: [],
    fallbackUsed: true,
  }),
};

function buildAdapters() {
  const sessionAdapter = new InMemorySessionAdapter({ idFactory: makeIdFactory("session"), clock });
  const adapters: CourseRuntimeAdapters = {
    assetResolver: { resolve: (p) => `/resolved/${p}` },
    sessionAdapter,
    openingGenerator: fallbackGenerator,
    closingGenerator: fallbackGenerator,
  };
  return { sessionAdapter, adapters };
}

/**
 * A SessionAdapter whose `create()` mimics the production API adapter's
 * get-or-create semantics (apps/web's apiSessionAdapter over the server's
 * get-or-create POST): it does NOT mint a fresh session — it always returns
 * (and mutates) the one pre-seeded session, regardless of the input. This is
 * what a real host that never passes a `sessionId` prop actually gets back,
 * so tests here exercise the same "no sessionId → create() must still drive
 * resume" path production hits.
 */
function buildSeededAdapters(seed: CourseSession) {
  let session: CourseSession = structuredClone(seed);
  const setStatusCalls: Array<CourseSession["status"]> = [];

  const sessionAdapter: SessionAdapter = {
    async load(sessionId) {
      return session.id === sessionId ? structuredClone(session) : null;
    },
    async create() {
      // Get-or-create: the seeded session already exists server-side.
      return structuredClone(session);
    },
    async appendEvent(_sessionId, event) {
      session.events.push(structuredClone(event));
    },
    async saveSliceState(_sessionId, sliceId, state) {
      session.sliceStates[sliceId] = structuredClone(state);
    },
    async saveScene(_sessionId, which, result) {
      session[which] = structuredClone(result);
    },
    async setStatus(_sessionId, status) {
      setStatusCalls.push(status);
      session.status = status;
    },
    async setCurrent(_sessionId, current) {
      session.current = current ? structuredClone(current) : undefined;
    },
    async setDefinitionHash(_sessionId, hash) {
      session.courseDefinitionHash = hash;
    },
    async resetProgress(_sessionId) {
      session.current = undefined;
      session.sliceStates = {};
    },
  };

  const adapters: CourseRuntimeAdapters = {
    assetResolver: { resolve: (p) => `/resolved/${p}` },
    sessionAdapter,
    openingGenerator: fallbackGenerator,
    closingGenerator: fallbackGenerator,
  };
  return { adapters, setStatusCalls, getSession: () => session };
}

describe("CoursePlayer end-to-end", () => {
  it("shows a visible loading surface (spinner + label) on first entry, not an empty white box", () => {
    const { adapters } = buildAdapters();
    const { container } = render(
      <AudioEngineProvider value={new FakeAudioEngine()}>
        <CoursePlayer
          document={staticCourseDocument}
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );
    // Synchronously after mount the async init hasn't resolved — the loading
    // phase must render a real spinner + label, never a blank div.
    const loading = container.querySelector(".course-loading");
    expect(loading).not.toBeNull();
    expect(loading!.querySelector(".course-loading__spinner")).not.toBeNull();
    expect(loading!.textContent).toContain("正在加载课程");
  });


  it("plays Opening → Slices → Closing driven by the workflow; Closing is visible and the session stays 'closing' until the learner dismisses it, only then firing onComplete (P1-03)", async () => {
    const { sessionAdapter, adapters } = buildAdapters();
    const engine = new FakeAudioEngine();
    let bus: RuntimeEventBus | null = null;
    const onComplete = vi.fn();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
          onBusReady={(b) => {
            bus = b;
          }}
          onComplete={onComplete}
        />
      </AudioEngineProvider>,
    );

    // Opening renders with the fixed start action + the fallback greeting.
    await screen.findByText("一起开始吧");
    expect(screen.getByText(/欢迎来到这门演示课程/)).toBeInTheDocument();

    // Start → slice one mounts and plays its narration.
    await userEvent.click(screen.getByRole("button", { name: "一起开始吧" }));
    expect(engine.calls.some((c) => c.url === "/resolved/audio/s1.mp3")).toBe(true);

    // slice one: narration.ended → reveal, then student.continue → navigate.
    act(() => engine.fireEnded());
    expect(document.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    act(() => bus!.bindSlice("part-one", "slice-one")("s1-continue", "student.continue"));

    // slice two mounted and playing its narration.
    expect(engine.calls.some((c) => c.url === "/resolved/audio/s2.mp3")).toBe(true);

    // slice two: narration.ended → navigate past the last slice → Closing.
    act(() => engine.fireEnded());

    // Closing renders the prepared summary + takeaways — the learner ACTUALLY
    // sees it (this is the P1-03 fix: it must render before status flips to
    // "completed", not after).
    await screen.findByText("你走完了两个片段，理解了演示流程。");
    expect(screen.getByText("片段按顺序推进")).toBeInTheDocument();
    expect(screen.getByText("讲解结束触发揭示")).toBeInTheDocument();

    // Still "closing", not "completed" — and onComplete has NOT fired — while
    // the Closing scene is up and the learner hasn't dismissed it yet.
    const midSession = await sessionAdapter.load("session-1");
    expect(midSession!.status).toBe("closing");
    expect(midSession!.closing?.fallbackUsed).toBe(true);
    expect(onComplete).not.toHaveBeenCalled();

    // The learner dismisses via the explicit completion control — only THEN
    // does the session become "completed" and onComplete fire.
    await userEvent.click(screen.getByRole("button", { name: "完成课程" }));
    expect(onComplete).toHaveBeenCalledTimes(1);

    const finalSession = await sessionAdapter.load("session-1");
    expect(finalSession!.status).toBe("completed");
  });

  it("resumes a 'closing' (not-yet-dismissed) session returned by get-or-create: renders Closing directly without regenerating, and dismissing it still completes + fires onComplete", async () => {
    const seed: CourseSession = {
      id: "server-session-closing",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "closing",
      opening: { text: "欢迎回来", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      closing: { text: "已保存的收尾", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {},
      events: [],
    };
    const { adapters, setStatusCalls } = buildSeededAdapters(seed);
    const engine = new FakeAudioEngine();
    const onComplete = vi.fn();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
          onComplete={onComplete}
        />
      </AudioEngineProvider>,
    );

    // Restored straight to the saved Closing narration — never regenerated,
    // never touched status on the way in.
    await screen.findByText("已保存的收尾");
    expect(setStatusCalls).toEqual([]);
    expect(onComplete).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "完成课程" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(setStatusCalls).toEqual(["completed"]);
  });

  it("resumes an existing mid-Slice session: lands on the same Slice + workflow step + block state, not Opening/index 0", async () => {
    const { sessionAdapter, adapters } = buildAdapters();
    const engine = new FakeAudioEngine();

    // Seed a prior session already parked mid-slice-one, at the "reveal" step
    // (reached only after narration.ended — never the initial "intro" step).
    const priorSession = await sessionAdapter.create({ courseId: "static-demo-course", studentId: "student-1" });
    await sessionAdapter.saveScene(priorSession.id, "opening", {
      text: "欢迎回来",
      generatedAt: clock(),
      usedSignalTypes: [],
      fallbackUsed: true,
    });
    await sessionAdapter.setStatus(priorSession.id, "in-progress");
    const revealState: SliceSessionState = {
      status: "in-progress",
      currentWorkflowStepId: "reveal",
      startedAt: clock(),
      elapsedSeconds: 12,
      blockStates: {
        "s1-intro-text": { visible: true, enabled: true, completed: false },
        "s1-reveal-text": { visible: true, enabled: true, completed: false },
        "s1-continue": { visible: true, enabled: true, completed: false },
      },
    };
    await sessionAdapter.saveSliceState(priorSession.id, "slice-one", revealState);
    await sessionAdapter.setCurrent(priorSession.id, { partId: "part-one", sliceId: "slice-one", workflowStepId: "reveal" });

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          adapters={adapters}
          studentId="student-1"
          sessionId={priorSession.id}
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    // Landed directly on slice-one's "reveal" step: the reveal block is already
    // visible without ever firing narration.ended — a fresh mount would start at
    // "intro" (reveal hidden, only after narration.ended does it show).
    await waitFor(() => {
      expect(document.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    });
    // Never showed the Opening scene or slice-two — restored straight to slice-one.
    expect(screen.queryByText("一起开始吧")).toBeNull();
    expect(document.querySelector('[data-block-id="s2-text"]')).toBeNull();
    // "reveal" enterActions don't playNarration — the intro narration never replayed.
    expect(engine.calls.some((c) => c.op === "play" && c.url === "/resolved/audio/s1.mp3")).toBe(false);
  });

  it("resumes an in-progress session returned by get-or-create even with NO client sessionId prop (production host path): restores mid-Slice, never shows Opening, never resets status to 'opening'", async () => {
    const seed: CourseSession = {
      id: "server-session-1",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "in-progress",
      current: { partId: "part-one", sliceId: "slice-one", workflowStepId: "reveal" },
      opening: { text: "欢迎回来", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {
        "slice-one": {
          status: "in-progress",
          currentWorkflowStepId: "reveal",
          startedAt: clock(),
          elapsedSeconds: 12,
          blockStates: {
            "s1-intro-text": { visible: true, enabled: true, completed: false },
            "s1-reveal-text": { visible: true, enabled: true, completed: false },
            "s1-continue": { visible: true, enabled: true, completed: false },
          },
        },
      },
      events: [],
    };
    const { adapters, setStatusCalls } = buildSeededAdapters(seed);
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          adapters={adapters}
          studentId="student-1"
          // No sessionId prop — this is exactly what RuntimeCoursePlayer does
          // in production; resume must still key off the get-or-create result.
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    // Landed directly on slice-one's "reveal" step, matching the seeded state.
    await waitFor(() => {
      expect(document.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    });
    // Never showed the fresh Opening scene or reset to slice index 0's intro.
    expect(screen.queryByText("一起开始吧")).toBeNull();
    expect(document.querySelector('[data-block-id="s2-text"]')).toBeNull();
    // The server's in-progress status must never be clobbered back to "opening".
    expect(setStatusCalls).not.toContain("opening");
  });

  it("resumes a completed session returned by get-or-create with NO client sessionId prop: renders Closing/summary directly, never resets", async () => {
    const seed: CourseSession = {
      id: "server-session-2",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "completed",
      opening: { text: "欢迎回来", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      closing: { text: "已保存的收尾", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {},
      events: [],
    };
    const { adapters, setStatusCalls } = buildSeededAdapters(seed);
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    // Restored straight to the saved Closing narration + the course's summary.
    await screen.findByText("已保存的收尾");
    expect(screen.getByText("你走完了两个片段，理解了演示流程。")).toBeInTheDocument();
    // Never showed Opening or any Slice.
    expect(screen.queryByText("一起开始吧")).toBeNull();
    expect(document.querySelector(".course-slice")).toBeNull();
    // A completed session's status must never be touched, let alone reset.
    expect(setStatusCalls).toEqual([]);
  });

  it("上一步 returns to an already-completed Slice restored (no re-fired navigate/narration), offers replay, and 下一步 returns forward (§Slice4 / P1-05)", async () => {
    const { adapters } = buildAdapters();
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer document={staticCourseDocument} adapters={adapters} studentId="student-1" idFactory={makeIdFactory("ev")} clock={clock} />
      </AudioEngineProvider>,
    );

    await screen.findByText("一起开始吧");
    await userEvent.click(screen.getByRole("button", { name: "一起开始吧" }));

    // 上一步 is unavailable on the very first Slice.
    expect(screen.getByRole("button", { name: "上一步" })).toBeDisabled();

    // Finish slice-one through the real P1-05 producer (not the raw bus) —
    // narration.ended → reveal, then the 继续 control → done (completeSlice + navigate).
    act(() => engine.fireEnded());
    await userEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(document.querySelector('[data-block-id="s2-text"]')).not.toBeNull();
    const playsBeforePrevious = engine.calls.filter((c) => c.op === "play").length;

    // 上一步 returns to slice-one, showing it completed — not frozen, and
    // crucially NOT re-firing its "done" step's completeSlice+navigate (which
    // would otherwise immediately bounce straight back to slice-two).
    await userEvent.click(screen.getByRole("button", { name: "上一步" }));
    expect(document.querySelector('[data-block-id="s2-text"]')).toBeNull();
    expect(document.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    expect(engine.calls.filter((c) => c.op === "play").length).toBe(playsBeforePrevious);
    expect(screen.getByRole("button", { name: "上一步" })).toBeDisabled();

    // The explicit replay path re-runs slice-one from initial: reveal hides
    // again and its narration genuinely plays again.
    await userEvent.click(screen.getByRole("button", { name: "重新开始本节" }));
    expect(document.querySelector('[data-block-id="s1-reveal-text"]')).toHaveAttribute("hidden");
    expect(engine.calls.filter((c) => c.op === "play").length).toBeGreaterThan(playsBeforePrevious);

    // Finishing the replayed run (its own explicit `navigate`) lands back on
    // slice-two, same as the very first pass — Previous/replay didn't corrupt
    // the forward walk.
    act(() => engine.fireEnded());
    await userEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(document.querySelector('[data-block-id="s2-text"]')).not.toBeNull();
  });

  it("renders the error surface for a structurally-invalid document and never mounts a slice", () => {
    const { adapters } = buildAdapters();
    render(
      <CoursePlayer
        document={{ schemaVersion: "2.0", course: { id: "bad" } }}
        adapters={adapters}
        studentId="student-1"
        idFactory={makeIdFactory("ev")}
        clock={clock}
      />,
    );
    expect(screen.getByRole("alert")).toHaveAttribute("data-course-error", "true");
    expect(document.querySelector(".course-slice")).toBeNull();
    expect(screen.queryByText("一起开始吧")).toBeNull();
    // §Slice5 / P1-06 (D6) — even the diagnostic error surface renders inside
    // the one-screen shell, not a bare page-scrolling fragment.
    expect(document.querySelector('[data-course-shell="true"]')).not.toBeNull();
  });

  it("wraps every phase in the one-screen course-shell (§Slice5 / P1-06, D6)", async () => {
    const { adapters } = buildAdapters();
    render(<CoursePlayer document={staticCourseDocument} adapters={adapters} studentId="student-1" idFactory={makeIdFactory("ev")} clock={clock} />);

    await screen.findByText("一起开始吧");
    const shell = document.querySelector('[data-course-shell="true"]');
    expect(shell).not.toBeNull();
    expect(shell).toHaveClass("course-shell");
    // The Opening scene renders INSIDE the shell, not as a sibling of it.
    expect(shell!.textContent).toContain("一起开始吧");
  });
});

// D5 / P2-08 — a session's own recorded `courseDefinitionHash` vs. the host's
// `definitionHash` prop (the CURRENT definition's content hash): a
// disagreement means the course was edited since this session was built, so
// its slice/step/block state may reference removed ids and must never be
// restored; a match (or an absent recorded hash — back-compat for sessions
// persisted before this field existed) resumes exactly as before.
describe("CoursePlayer definition-revision policy (D5 / P2-08)", () => {
  it("resets a session whose recorded hash disagrees with the current definition's hash: discards its progress, stamps the new hash, and shows a dismissible notice", async () => {
    const seed: CourseSession = {
      id: "server-session-stale",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "in-progress",
      current: { partId: "part-one", sliceId: "slice-two", workflowStepId: "intro" },
      opening: { text: "旧版开场白", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {
        "slice-two": { status: "in-progress", currentWorkflowStepId: "intro", startedAt: clock(), elapsedSeconds: 5, blockStates: {} },
      },
      events: [],
      courseDefinitionHash: "old-hash",
    };
    const { adapters, getSession } = buildSeededAdapters(seed);
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          definitionHash="new-hash"
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    // Fresh Opening — never resumed straight to the stale `current` (slice-two).
    await screen.findByText("一起开始吧");
    expect(screen.queryByText("旧版开场白")).toBeNull();
    expect(document.querySelector('[data-block-id="s2-text"]')).toBeNull();

    // The notice is visible and dismissible.
    const notice = screen.getByTestId("course-revision-notice");
    expect(notice).toHaveTextContent("课程已更新，进度已重置");
    await userEvent.click(screen.getByRole("button", { name: "知道了" }));
    expect(screen.queryByTestId("course-revision-notice")).toBeNull();

    // The new hash is stamped onto the session so its NEXT resume compares clean.
    await waitFor(() => expect(getSession().courseDefinitionHash).toBe("new-hash"));
  });

  // Durability regression: a stale-hash reset that only cleared the
  // renderer's in-memory `sliceStatesRef` (never the adapter's PERSISTED
  // `current`/`sliceStates`) looked fixed on the SAME mount but silently
  // resurrected the discarded progress on the NEXT one — the freshly
  // stamped hash would then match, so the resume guard `restored.current
  // != null` would fire again and jump straight back to the stale (possibly
  // now-removed) slice/step. This test re-mounts against the same held
  // session to prove the persisted progress was actually cleared, not just
  // the in-memory cache.
  it("a stale-hash reset is durable across a reload: the persisted current/sliceStates are cleared, so a SECOND mount (now with a matching hash) does not resurrect the discarded slice", async () => {
    const seed: CourseSession = {
      id: "server-session-stale-reload",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "in-progress",
      current: { partId: "part-one", sliceId: "slice-two", workflowStepId: "intro" },
      opening: { text: "旧版开场白", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {
        "slice-two": { status: "in-progress", currentWorkflowStepId: "intro", startedAt: clock(), elapsedSeconds: 5, blockStates: {} },
      },
      events: [],
      courseDefinitionHash: "old-hash",
    };
    const { adapters, getSession } = buildSeededAdapters(seed);

    // First mount: hash mismatches ("old-hash" vs "new-hash") — resets.
    const engine1 = new FakeAudioEngine();
    const first = render(
      <AudioEngineProvider value={engine1}>
        <CoursePlayer
          document={staticCourseDocument}
          definitionHash="new-hash"
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev1")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );
    await screen.findByText("一起开始吧");
    await waitFor(() => expect(getSession().courseDefinitionHash).toBe("new-hash"));

    // The PERSISTED session — not just the renderer's local cache — must be
    // cleared: this is the held "server" copy the seeded adapter returns to
    // every subsequent load()/create().
    expect(getSession().current).toBeUndefined();
    expect(getSession().sliceStates).toEqual({});
    first.unmount();

    // Second mount ("reload"): the session's hash now matches the current
    // definition's hash, so it is no longer stale — the resume guard would
    // fire on any leftover `current`. It must find none.
    const engine2 = new FakeAudioEngine();
    render(
      <AudioEngineProvider value={engine2}>
        <CoursePlayer
          document={staticCourseDocument}
          definitionHash="new-hash"
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev2")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    // Fresh Opening again — never resumed straight into slice-two's "intro"
    // step, and no revision notice this time (hash matches, not stale).
    await screen.findByText("一起开始吧");
    expect(document.querySelector('[data-block-id="s2-text"]')).toBeNull();
    expect(screen.queryByTestId("course-revision-notice")).toBeNull();
  });

  it("resumes normally (no reset, no notice) when the session's recorded hash matches the current definition's hash", async () => {
    const seed: CourseSession = {
      id: "server-session-match",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "in-progress",
      current: { partId: "part-one", sliceId: "slice-one", workflowStepId: "reveal" },
      opening: { text: "欢迎回来", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {
        "slice-one": {
          status: "in-progress",
          currentWorkflowStepId: "reveal",
          startedAt: clock(),
          elapsedSeconds: 12,
          blockStates: {
            "s1-intro-text": { visible: true, enabled: true, completed: false },
            "s1-reveal-text": { visible: true, enabled: true, completed: false },
            "s1-continue": { visible: true, enabled: true, completed: false },
          },
        },
      },
      events: [],
      courseDefinitionHash: "same-hash",
    };
    const { adapters } = buildSeededAdapters(seed);
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          definitionHash="same-hash"
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    await waitFor(() => {
      expect(document.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    });
    expect(screen.queryByText("一起开始吧")).toBeNull();
    expect(screen.queryByTestId("course-revision-notice")).toBeNull();
  });

  it("treats a session with NO recorded hash as compatible (back-compat) even when the host supplies a definitionHash: resumes normally, no notice, and stamps the hash going forward", async () => {
    const seed: CourseSession = {
      id: "server-session-no-hash",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "in-progress",
      current: { partId: "part-one", sliceId: "slice-one", workflowStepId: "reveal" },
      opening: { text: "欢迎回来", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {
        "slice-one": {
          status: "in-progress",
          currentWorkflowStepId: "reveal",
          startedAt: clock(),
          elapsedSeconds: 12,
          blockStates: {
            "s1-intro-text": { visible: true, enabled: true, completed: false },
            "s1-reveal-text": { visible: true, enabled: true, completed: false },
            "s1-continue": { visible: true, enabled: true, completed: false },
          },
        },
      },
      events: [],
      // No courseDefinitionHash — a session persisted before this field existed.
    };
    const { adapters, getSession } = buildSeededAdapters(seed);
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={staticCourseDocument}
          definitionHash="new-hash"
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    await waitFor(() => {
      expect(document.querySelector('[data-block-id="s1-reveal-text"]')).not.toHaveAttribute("hidden");
    });
    expect(screen.queryByText("一起开始吧")).toBeNull();
    expect(screen.queryByTestId("course-revision-notice")).toBeNull();
    await waitFor(() => expect(getSession().courseDefinitionHash).toBe("new-hash"));
  });
});

// P2-05 — the Opening/Closing personalization inputs must be REAL, never `{}`
// placeholders: signalValues comes only from the host's own signalResolver
// (never fabricated by the renderer), and sessionEvidence comes only from the
// actual validated CourseSession's recorded state, both scoped to exactly the
// course's own `allowedSignals`.
describe("CoursePlayer personalization inputs (P2-05)", () => {
  it("passes the host signalResolver's result as the Opening's signalValues, called with exactly the course's allowedSignals", async () => {
    const personalizedOpeningDocument = {
      ...staticCourseDocument,
      course: {
        ...staticCourseDocument.course,
        opening: {
          ...staticCourseDocument.course.opening,
          personalization: { enabled: true, allowedSignals: ["recent-course-topics"] },
        },
      },
    };
    const { adapters } = buildAdapters();
    const capturedOpeningInputs: SceneGenerationInput[] = [];
    adapters.openingGenerator = {
      generate: async (input) => {
        capturedOpeningInputs.push(input);
        return { text: input.fallback.text, generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true };
      },
    };
    const signalResolver = vi.fn((_allowed: string[]) => ({ "recent-course-topics": "上次学了论证结构" }));

    render(
      <CoursePlayer
        document={personalizedOpeningDocument}
        adapters={adapters}
        studentId="student-1"
        idFactory={makeIdFactory("ev")}
        clock={clock}
        signalResolver={signalResolver}
      />,
    );

    await waitFor(() => expect(capturedOpeningInputs.length).toBe(1));
    expect(signalResolver).toHaveBeenCalledWith(["recent-course-topics"]);
    const input = capturedOpeningInputs[0]!;
    expect(input.which).toBe("opening");
    if (input.which === "opening") {
      expect(input.signalValues).toEqual({ "recent-course-topics": "上次学了论证结构" });
    }
  });

  it("never calls the resolver, and signalValues stays empty, when the Opening's personalization is disabled", async () => {
    const { adapters } = buildAdapters();
    const capturedOpeningInputs: SceneGenerationInput[] = [];
    adapters.openingGenerator = {
      generate: async (input) => {
        capturedOpeningInputs.push(input);
        return { text: input.fallback.text, generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true };
      },
    };
    const signalResolver = vi.fn(() => ({ "recent-course-topics": "should never be reached" }));

    render(
      <CoursePlayer
        document={staticCourseDocument} // opening.personalization.enabled === false
        adapters={adapters}
        studentId="student-1"
        idFactory={makeIdFactory("ev")}
        clock={clock}
        signalResolver={signalResolver}
      />,
    );

    await waitFor(() => expect(capturedOpeningInputs.length).toBe(1));
    expect(signalResolver).not.toHaveBeenCalled();
    const input = capturedOpeningInputs[0]!;
    if (input.which === "opening") expect(input.signalValues).toEqual({});
  });

  it("derives the Closing's sessionEvidence from the session's own recorded answers/attempts/time-on-slice, omitting a permitted signal with no recorded data", async () => {
    const personalizedClosingDocument = {
      ...staticCourseDocument,
      course: {
        ...staticCourseDocument.course,
        closing: {
          ...staticCourseDocument.course.closing,
          personalization: {
            enabled: true,
            // "interaction-results" is permitted but nothing was ever recorded
            // for it below — it must be OMITTED from the evidence, not sent as
            // an empty placeholder.
            allowedSignals: ["answers", "attempts", "time-on-slice", "interaction-results"],
          },
        },
      },
    };

    const seed: CourseSession = {
      id: "server-session-evidence",
      courseId: "static-demo-course",
      courseSchemaVersion: "2.0",
      studentId: "student-1",
      status: "in-progress",
      current: { partId: "part-one", sliceId: "slice-two", workflowStepId: "intro" },
      opening: { text: "欢迎回来", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true },
      sliceStates: {
        "slice-one": {
          status: "completed",
          currentWorkflowStepId: "done",
          startedAt: clock(),
          completedAt: clock(),
          elapsedSeconds: 12,
          blockStates: {
            "s1-intro-text": { visible: true, enabled: true, completed: true },
            "s1-reveal-text": { visible: true, enabled: true, completed: true, answer: "已读", attempts: 1 },
            "s1-continue": { visible: true, enabled: true, completed: true },
          },
        },
      },
      events: [],
    };
    const { adapters } = buildSeededAdapters(seed);
    const capturedClosingInputs: SceneGenerationInput[] = [];
    adapters.closingGenerator = {
      generate: async (input) => {
        capturedClosingInputs.push(input);
        return { text: input.fallback.text, generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true };
      },
    };
    const engine = new FakeAudioEngine();

    render(
      <AudioEngineProvider value={engine}>
        <CoursePlayer
          document={personalizedClosingDocument}
          adapters={adapters}
          studentId="student-1"
          idFactory={makeIdFactory("ev")}
          clock={clock}
        />
      </AudioEngineProvider>,
    );

    // Resumes straight into slice-two (per the seeded `current`) — finish it
    // (its only transition is narration.ended) to reach Closing.
    await waitFor(() => {
      expect(document.querySelector('[data-block-id="s2-text"]')).not.toBeNull();
    });
    act(() => engine.fireEnded());

    await waitFor(() => expect(capturedClosingInputs.length).toBe(1));
    const input = capturedClosingInputs[0]!;
    expect(input.which).toBe("closing");
    if (input.which === "closing") {
      expect(input.sessionEvidence).toEqual({
        answers: { "slice-one": { "s1-reveal-text": "已读" } },
        attempts: { "slice-one": { "s1-reveal-text": 1 } },
        "time-on-slice": { "slice-one": 12 },
      });
    }
  });
});
