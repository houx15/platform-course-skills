import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BlockSessionState } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";
import { VideoRenderer } from "../../src/blocks/media/VideoRenderer";
import type { VideoBlock } from "../../src/blocks/types";
import { VideoEngineProvider } from "../../src/media/videoEngine";
import { MediaHandleRegistry, MediaHandleRegistryProvider } from "../../src/media/mediaRegistry";
import { AudioArbiter, AudioArbiterProvider } from "../../src/media/audioArbiter";
import { FakeVideoEngine } from "../support/fakeVideoEngine";

const assetResolver = { resolve: (p: string) => `/resolved/${p}` };

interface Recorded {
  sourceId: string;
  type: string;
  payload: unknown;
}

const baseState: BlockSessionState = { visible: true, enabled: true, completed: false };

function renderVideo(block: VideoBlock, enabled = true) {
  const events: Recorded[] = [];
  const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
  const engine = new FakeVideoEngine();
  const registry = new MediaHandleRegistry();

  const utils = render(
    <MediaHandleRegistryProvider value={registry}>
      <VideoEngineProvider value={engine.factory}>
        <VideoRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled={enabled} emit={emit} />
      </VideoEngineProvider>
    </MediaHandleRegistryProvider>,
  );
  return { ...utils, events, engine, registry };
}

const endedRuleBlock: VideoBlock = {
  id: "case-video",
  type: "video",
  source: "assets/videos/case.mp4",
  poster: "assets/images/case-poster.jpg",
  captions: "assets/captions/case.en.vtt",
  durationSeconds: 90,
  completion: { rule: "video-ended" },
};

const noCompletionBlock: VideoBlock = {
  id: "plain-video",
  type: "video",
  source: "assets/videos/plain.mp4",
};

const typeNames = (events: Recorded[]) => events.map((e) => e.type);

describe("VideoRenderer", () => {
  it("registers a media handle whose play drives the engine and emits video.started", () => {
    const { engine, registry, events } = renderVideo(endedRuleBlock);
    const handle = registry.get("case-video");
    expect(handle).toBeDefined();
    act(() => handle!.play());
    expect(engine.calls).toContain("play");
    expect(typeNames(events)).toContain("video.started");
  });

  it("handle pause drives the engine and emits video.paused with the current position", () => {
    const { engine, registry, events } = renderVideo(endedRuleBlock);
    engine.advanceTo(37);
    act(() => registry.get("case-video")!.pause());
    expect(engine.calls).toContain("pause");
    expect(typeNames(events)).toContain("video.paused");
    expect(events.find((e) => e.type === "video.paused")).toMatchObject({ payload: { positionSeconds: 37 } });
  });

  it("engine ended with completion video-ended emits video.ended (with position) then block.completed", () => {
    const { engine, events } = renderVideo(endedRuleBlock);
    engine.advanceTo(90);
    act(() => engine.fireEnded());
    expect(typeNames(events)).toEqual(["video.ended", "block.completed"]);
    expect(events[0]).toMatchObject({ sourceId: "case-video", payload: { positionSeconds: 90 } });
  });

  it("with no completion rule, ended emits video.ended but NOT block.completed", () => {
    const { engine, events } = renderVideo(noCompletionBlock);
    act(() => engine.fireEnded());
    expect(typeNames(events)).toEqual(["video.ended"]);
    expect(typeNames(events)).not.toContain("block.completed");
  });

  it("renders a <video> with the resolved source, poster, and a caption track", () => {
    const { container } = renderVideo(endedRuleBlock);
    const video = container.querySelector("video")!;
    expect(video).toBeInTheDocument();
    expect(video).toHaveAttribute("src", "/resolved/assets/videos/case.mp4");
    expect(video).toHaveAttribute("poster", "/resolved/assets/images/case-poster.jpg");
    const track = container.querySelector("track");
    expect(track).toHaveAttribute("src", "/resolved/assets/captions/case.en.vtt");
    expect(track).toHaveAttribute("kind", "captions");
  });

  it("block.completed is emitted at most once even if ended fires twice", () => {
    const { engine, events } = renderVideo(endedRuleBlock);
    act(() => engine.fireEnded());
    act(() => engine.fireEnded());
    expect(events.filter((e) => e.type === "block.completed")).toHaveLength(1);
  });

  it("honors the enabled prop: hides the native controls and ignores play/pause", () => {
    const { container, engine, registry } = renderVideo(endedRuleBlock, false);
    const video = container.querySelector("video")!;
    expect(video).not.toHaveAttribute("controls");

    // Even the workflow's imperative handle is a no-op while disabled.
    act(() => registry.get("case-video")!.play());
    expect(engine.calls).not.toContain("play");
  });

  it("folds the native <video> play/pause events (not only the custom buttons) into the event stream (P2-03)", () => {
    const events: Recorded[] = [];
    const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
    const registry = new MediaHandleRegistry();
    // No VideoEngineProvider: this exercises the real HtmlVideoEngine bound to
    // the actual <video> element, so a DOM "play"/"pause" event — however it
    // originated (native controls included) — is what drives the emitted
    // events, not the custom button handlers themselves.
    const { container } = render(
      <MediaHandleRegistryProvider value={registry}>
        <VideoRenderer block={endedRuleBlock} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} />
      </MediaHandleRegistryProvider>,
    );
    const video = container.querySelector("video")!;

    act(() => {
      video.dispatchEvent(new Event("play"));
    });
    expect(typeNames(events)).toContain("video.started");

    act(() => {
      video.currentTime = 12;
      video.dispatchEvent(new Event("pause"));
    });
    const paused = events.find((e) => e.type === "video.paused");
    expect(paused).toMatchObject({ payload: { positionSeconds: 12 } });
  });

  it("surfaces a play() rejection with a learner-recoverable retry affordance (P2-03)", async () => {
    const user = userEvent.setup();
    const { engine, registry } = renderVideo(endedRuleBlock);
    // Playback is driven by the native player / workflow handle now (no custom
    // buttons) — trigger it via the media handle, then reject it.
    act(() => registry.get("case-video")!.play());
    act(() => engine.firePlayError(new Error("NotAllowedError")));

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("播放未能开始");
    expect(engine.calls.filter((c) => c === "play")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "重试播放" }));
    expect(engine.calls.filter((c) => c === "play")).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reset re-enables gating: clears the completed flag so a subsequent ended can re-complete", () => {
    const { engine, events, registry } = renderVideo(endedRuleBlock);
    act(() => engine.fireEnded());
    expect(events.filter((e) => e.type === "block.completed")).toHaveLength(1);

    act(() => registry.get("case-video")!.reset());
    expect(engine.calls).toContain("reset");

    act(() => engine.fireEnded());
    expect(events.filter((e) => e.type === "block.completed")).toHaveLength(2);
  });

  // P1-11: a signed-URL refresh (RuntimeCoursePlayer re-signing before
  // expiresAt) re-renders the whole course tree. An ACTIVE/playing video must
  // NOT reload — that would reset currentTime and drop cue state — just
  // because an unrelated background refresh happened.
  describe("URL-refresh safety (P1-11)", () => {
    function renderRefreshable(block: VideoBlock) {
      let current = "v1.mp4";
      const resolver = { resolve: () => current };
      const events: Recorded[] = [];
      const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
      const engine = new FakeVideoEngine();
      const registry = new MediaHandleRegistry();
      // A FRESH element (not a cached, reused JSX reference) each call — a
      // parent state update (RuntimeCoursePlayer's `setRefreshTick`) always
      // produces new element/prop objects for its subtree on a real
      // re-render, so reusing one cached element across `rerender()` calls
      // would let React bail out at this fiber via prop-identity and never
      // actually re-invoke VideoRenderer — masking the exact bug P1-11 fixes.
      const buildUi = () => (
        <MediaHandleRegistryProvider value={registry}>
          <VideoEngineProvider value={engine.factory}>
            <VideoRenderer block={block} assetResolver={resolver} state={baseState} visible enabled emit={emit} />
          </VideoEngineProvider>
        </MediaHandleRegistryProvider>
      );
      const utils = render(buildUi());
      return {
        ...utils,
        events,
        engine,
        registry,
        setResolved: (next: string) => {
          current = next;
        },
        rerenderSame: () => utils.rerender(buildUi()),
      };
    }

    it("does NOT change the video element's src on a background re-render while nothing changed", () => {
      const { container, setResolved, rerenderSame } = renderRefreshable(endedRuleBlock);
      const video = container.querySelector("video")!;
      expect(video).toHaveAttribute("src", "v1.mp4");

      // Simulate a URL refresh landing (the resolver would now return
      // something different) followed by RuntimeCoursePlayer's global
      // re-render tick — but nothing has told the video it's safe to swap.
      setResolved("v2-renewed.mp4");
      rerenderSame();

      expect(video).toHaveAttribute("src", "v1.mp4"); // stable — no reload
    });

    it("on a load error, re-resolves the src, restores currentTime, and resumes playback if it was mid-play", () => {
      const { container, engine, registry, setResolved } = renderRefreshable(endedRuleBlock);
      const video = container.querySelector("video")!;

      act(() => registry.get("case-video")!.play());
      engine.advanceTo(42);
      setResolved("v2-renewed.mp4");

      act(() => {
        video.dispatchEvent(new Event("error"));
      });

      expect(video).toHaveAttribute("src", "v2-renewed.mp4");
      expect(engine.calls).toContain("seek:42");
      // resumed: a second play() call beyond the original registry-driven one
      expect(engine.calls.filter((c) => c === "play")).toHaveLength(2);
    });

    it("on pause, lazily picks up a renewed URL without forcing playback to resume", () => {
      const { container, engine, registry, setResolved } = renderRefreshable(endedRuleBlock);
      const video = container.querySelector("video")!;

      act(() => registry.get("case-video")!.play());
      engine.advanceTo(17);
      setResolved("v2-renewed.mp4");
      act(() => registry.get("case-video")!.pause());

      expect(video).toHaveAttribute("src", "v2-renewed.mp4");
      expect(engine.calls).toContain("seek:17");
      expect(engine.calls.filter((c) => c === "play")).toHaveLength(1); // no resume
    });

    it("an error/pause with no actual URL change is a no-op — no extra seek/reload", () => {
      const { container, engine, registry } = renderRefreshable(endedRuleBlock);
      const video = container.querySelector("video")!;

      act(() => registry.get("case-video")!.pause());
      expect(video).toHaveAttribute("src", "v1.mp4");
      expect(engine.calls.some((c) => c.startsWith("seek:"))).toBe(false);
    });
  });

  // P1-09/D3: video is priority 2 in the cross-block single-audible-source
  // arbiter — below narration, above interactive-HTML music.
  describe("audio arbiter (P1-09/D3)", () => {
    function renderWithArbiter(block: VideoBlock, arbiter: AudioArbiter) {
      const events: Recorded[] = [];
      const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
      const engine = new FakeVideoEngine();
      const registry = new MediaHandleRegistry();
      const utils = render(
        <AudioArbiterProvider value={arbiter}>
          <MediaHandleRegistryProvider value={registry}>
            <VideoEngineProvider value={engine.factory}>
              <VideoRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} />
            </VideoEngineProvider>
          </MediaHandleRegistryProvider>
        </AudioArbiterProvider>,
      );
      return { ...utils, events, engine, registry };
    }

    it("registers as the arbiter's 'video' source on play; a higher-priority (narration) start pauses it", () => {
      const arbiter = new AudioArbiter();
      const { registry, engine } = renderWithArbiter(endedRuleBlock, arbiter);

      act(() => registry.get("case-video")!.play());
      expect(engine.calls).toContain("play");

      act(() => arbiter.notifyPlaying("narration", "n1", () => {}));
      expect(engine.calls).toContain("pause");
    });

    it("a lower-priority (htmlMusic) start does NOT pause an already-playing video", () => {
      const arbiter = new AudioArbiter();
      const { registry, engine } = renderWithArbiter(endedRuleBlock, arbiter);

      act(() => registry.get("case-video")!.play());
      engine.calls.length = 0;

      act(() => arbiter.notifyPlaying("htmlMusic", "h1", () => {}));
      expect(engine.calls).not.toContain("pause");
    });

    it("unregisters on its own pause/ended — a later narration start does not double-pause", () => {
      const arbiter = new AudioArbiter();
      const { registry, engine } = renderWithArbiter(endedRuleBlock, arbiter);

      act(() => registry.get("case-video")!.play());
      act(() => registry.get("case-video")!.pause());
      engine.calls.length = 0;

      act(() => arbiter.notifyPlaying("narration", "n1", () => {}));
      expect(engine.calls).not.toContain("pause"); // already paused itself — no stray extra pause call
    });
  });
});
