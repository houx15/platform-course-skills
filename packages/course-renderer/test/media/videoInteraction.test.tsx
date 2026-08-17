import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BlockSessionState, VideoInteractionDocument } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";
import { VideoRenderer } from "../../src/blocks/media/VideoRenderer";
import type { VideoBlock } from "../../src/blocks/types";
import { VideoEngineProvider } from "../../src/media/videoEngine";
import { MediaHandleRegistry, MediaHandleRegistryProvider } from "../../src/media/mediaRegistry";
import {
  InteractionLoaderProvider,
  InteractionLoadError,
  type InteractionLoader,
} from "../../src/blocks/media/VideoInteractionController";
import { FakeVideoEngine } from "../support/fakeVideoEngine";

const assetResolver = { resolve: (p: string) => `/resolved/${p}` };
const baseState: BlockSessionState = { visible: true, enabled: true, completed: false };

interface Recorded {
  sourceId: string;
  type: string;
  payload: unknown;
}

const gatedBlock: VideoBlock = {
  id: "case-video",
  type: "video",
  source: "assets/videos/case.mp4",
  durationSeconds: 195,
  interaction: { source: "interactions/video/case-video.json" },
  completion: { rule: "video-ended-and-interactions-completed" },
};

const doc: VideoInteractionDocument = {
  schemaVersion: "1.1",
  video: {
    blockId: "case-video",
    source: "assets/videos/case.mp4",
    durationSeconds: 195,
    cues: [
      {
        id: "prediction-check",
        atSeconds: 42,
        pauseVideo: true,
        required: true,
        prompt: "What do you predict will happen next?",
        activity: {
          type: "singleChoice",
          options: [
            { id: "same-basis", label: "The comparison basis will stay the same" },
            { id: "new-basis", label: "The comparison basis will change" },
          ],
          assessment: { mode: "survey" },
          completion: { rule: "submit-any" },
        },
      },
    ],
  },
};

const gradedCueBlock: VideoBlock = {
  id: "graded-video",
  type: "video",
  source: "assets/videos/graded.mp4",
  durationSeconds: 60,
  interaction: { source: "interactions/video/graded-video.json" },
  completion: { rule: "video-ended-and-interactions-completed" },
};

const gradedDoc: VideoInteractionDocument = {
  schemaVersion: "1.1",
  video: {
    blockId: "graded-video",
    source: "assets/videos/graded.mp4",
    durationSeconds: 60,
    cues: [
      {
        id: "quick-check",
        atSeconds: 15,
        pauseVideo: true,
        required: true,
        prompt: "Which basis matches?",
        activity: {
          type: "singleChoice",
          options: [
            { id: "same-basis", label: "The comparison basis will stay the same" },
            { id: "new-basis", label: "The comparison basis will change" },
          ],
          assessment: { mode: "graded", correctOptionId: "new-basis" },
          completion: { rule: "submit-any" },
        },
      },
    ],
  },
};

const optionalCueBlock: VideoBlock = {
  id: "optional-video",
  type: "video",
  source: "assets/videos/optional.mp4",
  durationSeconds: 60,
  interaction: { source: "interactions/video/optional-video.json" },
  completion: { rule: "video-ended" },
};

const optionalDoc: VideoInteractionDocument = {
  schemaVersion: "1.1",
  video: {
    blockId: "optional-video",
    source: "assets/videos/optional.mp4",
    durationSeconds: 60,
    cues: [
      {
        id: "optional-note",
        atSeconds: 20,
        pauseVideo: true,
        required: false,
        prompt: "Want to jot a quick note?",
        activity: {
          type: "fillBlank",
          assessment: { mode: "reflection", rubric: "Any reflection is fine." },
          completion: { rule: "submit-any" },
        },
      },
    ],
  },
};

/** Flushes the microtasks the async {@link InteractionLoader} resolves through, plus the resulting state update. */
async function flushLoad() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function renderWith(block: VideoBlock, loader: InteractionLoader) {
  const events: Recorded[] = [];
  const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
  const engine = new FakeVideoEngine();
  const registry = new MediaHandleRegistry();
  const utils = render(
    <InteractionLoaderProvider value={loader}>
      <MediaHandleRegistryProvider value={registry}>
        <VideoEngineProvider value={engine.factory}>
          <VideoRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} />
        </VideoEngineProvider>
      </MediaHandleRegistryProvider>
    </InteractionLoaderProvider>,
  );
  return { ...utils, events, engine, registry };
}

/**
 * The "production-style" mount: the SAME async loader interface + provider a
 * real host (Task 2's adapter) supplies, wired through `VideoRenderer` end to
 * end — no bespoke test-only sync shortcut.
 */
function renderGated() {
  return renderWith(gatedBlock, () => Promise.resolve(doc));
}

const typeNames = (events: Recorded[]) => events.map((e) => e.type);

describe("VideoInteractionController (cue timeline, §14)", () => {
  it("shows a loading status while the document is fetching, then at the cue time pauses, opens a dialog, and shows the cue activity", async () => {
    const { engine, events } = renderGated();
    expect(screen.getByRole("status")).toHaveTextContent("加载");
    await flushLoad();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    act(() => engine.advanceTo(42));
    expect(engine.calls).toContain("pause");
    expect(typeNames(events)).toContain("video.interaction.shown");
    const shown = events.find((e) => e.type === "video.interaction.shown");
    expect(shown).toMatchObject({ payload: { interactionId: "prediction-check" } });

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-label", "What do you predict will happen next?");
    expect(within(dialog).getByRole("radiogroup")).toBeInTheDocument();
  });

  it("completing the cue emits video.interaction.completed with the learner's typed result and resumes the video", async () => {
    const user = userEvent.setup();
    const { engine, events } = renderGated();
    await flushLoad();
    act(() => engine.advanceTo(42));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "The comparison basis will change" }));
    await user.click(within(dialog).getByRole("button", { name: "提交" }));

    const completed = events.find((e) => e.type === "video.interaction.completed");
    expect(completed).toMatchObject({ payload: { interactionId: "prediction-check", result: { value: "new-basis" } } });
    // Survey mode is ungraded: no correctness in the evidence.
    expect((completed!.payload as { result: { correct?: boolean } }).result.correct).toBeUndefined();
    // resumed: a play call comes after the pause
    expect(engine.calls).toContain("play");
    expect(engine.calls.lastIndexOf("play")).toBeGreaterThan(engine.calls.indexOf("pause"));
  });

  it("captures the inner activity's correctness into the typed result for a graded cue", async () => {
    const user = userEvent.setup();
    const { engine, events } = renderWith(gradedCueBlock, () => Promise.resolve(gradedDoc));
    await flushLoad();
    act(() => engine.advanceTo(15));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "The comparison basis will change" }));
    await user.click(within(dialog).getByRole("button", { name: "提交" }));

    const completed = events.find((e) => e.type === "video.interaction.completed");
    expect(completed).toMatchObject({
      payload: { interactionId: "quick-check", result: { correct: true, value: "new-basis" } },
    });
  });

  it("after the required cue completes, ended emits block.completed", async () => {
    const user = userEvent.setup();
    const { engine, events } = renderGated();
    await flushLoad();
    act(() => engine.advanceTo(42));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "The comparison basis will change" }));
    await user.click(within(dialog).getByRole("button", { name: "提交" }));
    act(() => engine.fireEnded());
    expect(typeNames(events)).toContain("block.completed");
  });

  it("ended with the required cue NOT completed does NOT emit block.completed", async () => {
    const { engine, events } = renderGated();
    await flushLoad();
    act(() => engine.fireEnded());
    expect(typeNames(events)).toContain("video.ended");
    expect(typeNames(events)).not.toContain("block.completed");
  });

  it("a cue fires only once (idempotent across repeated time updates)", async () => {
    const { engine, events } = renderGated();
    await flushLoad();
    act(() => engine.advanceTo(42));
    act(() => engine.advanceTo(43));
    act(() => engine.advanceTo(44));
    expect(events.filter((e) => e.type === "video.interaction.shown")).toHaveLength(1);
  });

  it("the cue dialog traps focus and restores focus to the previously focused element on close", async () => {
    const user = userEvent.setup();
    const { engine } = renderGated();
    await flushLoad();

    const outsideButton = document.createElement("button");
    outsideButton.textContent = "outside";
    document.body.appendChild(outsideButton);
    outsideButton.focus();
    expect(document.activeElement).toBe(outsideButton);

    act(() => engine.advanceTo(42));
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);

    const radios = within(dialog).getAllByRole("radio");
    const submit = within(dialog).getByRole("button", { name: "提交" });

    // Select an option first so the submit button is enabled (and thus
    // focusable) — otherwise it's a disabled control our trap correctly
    // excludes from the tab order.
    await user.click(radios[1]!);

    // Dispatched directly (rather than via userEvent.tab()) so this exercises
    // ONLY the trap's own keydown handling — userEvent.tab() additionally
    // simulates native radio-group roving-tabindex, which would otherwise
    // mask whether OUR wrap logic is what moved focus.
    submit.focus();
    fireEvent.keyDown(submit, { key: "Tab" });
    expect(document.activeElement).toBe(radios[0]);

    fireEvent.keyDown(radios[0]!, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(submit);

    await user.click(submit);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(outsideButton);
    outsideButton.remove();
  });

  it("a loader rejection shows a visible recoverable error, and retry re-attempts the load", async () => {
    const user = userEvent.setup();
    let calls = 0;
    const flaky: InteractionLoader = () => {
      calls += 1;
      if (calls === 1) return Promise.reject(new InteractionLoadError("not-found", "404"));
      return Promise.resolve(doc);
    };
    renderWith(gatedBlock, flaky);
    await flushLoad();

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("未能加载");
    await user.click(within(alert).getByRole("button", { name: "重试" }));
    await flushLoad();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("a resolved document that does not match the owning block (mismatch) shows a visible error instead of silently gating", async () => {
    const mismatched: VideoInteractionDocument = {
      ...doc,
      video: { ...doc.video, blockId: "some-other-block" },
    };
    renderWith(gatedBlock, () => Promise.resolve(mismatched));
    await flushLoad();
    expect(screen.getByRole("alert")).toHaveTextContent("不匹配");
  });

  it("a document whose referential shape is invalid (duplicate cue ids) shows a visible error", async () => {
    const invalid: VideoInteractionDocument = {
      ...doc,
      video: { ...doc.video, cues: [doc.video.cues[0]!, doc.video.cues[0]!] },
    };
    renderWith(gatedBlock, () => Promise.resolve(invalid));
    await flushLoad();
    expect(screen.getByRole("alert")).toHaveTextContent("未通过校验");
  });

  it("an optional cue's 跳过 control resumes without completing", async () => {
    const user = userEvent.setup();
    const { engine, events } = renderWith(optionalCueBlock, () => Promise.resolve(optionalDoc));
    await flushLoad();
    act(() => engine.advanceTo(20));

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "跳过" }));

    expect(typeNames(events)).toContain("video.interaction.skipped");
    expect(typeNames(events)).not.toContain("video.interaction.completed");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(engine.calls.lastIndexOf("play")).toBeGreaterThan(engine.calls.indexOf("pause"));
  });

  it("VideoRenderer's reset clears fired/completed cue state and re-arms the required gate", async () => {
    const user = userEvent.setup();
    const { engine, events, registry } = renderGated();
    await flushLoad();
    act(() => engine.advanceTo(42));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "The comparison basis will change" }));
    await user.click(within(dialog).getByRole("button", { name: "提交" }));
    act(() => engine.fireEnded());
    expect(typeNames(events).filter((t) => t === "block.completed")).toHaveLength(1);

    act(() => registry.get("case-video")!.reset());
    // Gate re-armed: ending again immediately must NOT re-complete.
    act(() => engine.fireEnded());
    expect(typeNames(events).filter((t) => t === "block.completed")).toHaveLength(1);

    // Fired/completed cleared: the cue can fire (and gate) again.
    act(() => engine.advanceTo(42));
    expect(events.filter((e) => e.type === "video.interaction.shown")).toHaveLength(2);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
