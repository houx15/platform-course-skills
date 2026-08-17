import { act, render, screen } from "@testing-library/react";
import { NarrationController, NarrationPlayer } from "../src/narration/NarrationPlayer";
import { FakeAudioEngine } from "./support/fakeAudioEngine";
import { AudioArbiter } from "../src/media/audioArbiter";
import type { NarrationDefinition } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";

const narration = (id: string): NarrationDefinition => ({ id, text: `transcript for ${id}`, audio: `audio/${id}.mp3` });

describe("NarrationController + NarrationPlayer", () => {
  it("emits narration.ended with the narration id when the engine reports ended", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const events: Array<{ sourceId: string; type: string }> = [];
    const emit: SliceEmitter = (sourceId, type) => events.push({ sourceId, type: String(type) });

    controller.play(narration("intro"), "/resolved/audio/intro.mp3", emit);
    engine.fireEnded();

    expect(events).toEqual([{ sourceId: "intro", type: "narration.ended" }]);
  });

  it("stops the current track before starting a second (single-track)", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const emit: SliceEmitter = () => {};

    controller.play(narration("one"), "/resolved/audio/one.mp3", emit);
    controller.play(narration("two"), "/resolved/audio/two.mp3", emit);

    const ops = engine.calls.map((c) => c.op);
    // first play, then a stop, then the second play — stop precedes the 2nd play.
    expect(ops).toEqual(["play", "stop", "play"]);
    expect(engine.calls[0]).toMatchObject({ url: "/resolved/audio/one.mp3" });
    expect(engine.calls[2]).toMatchObject({ url: "/resolved/audio/two.mp3" });
  });

  it("firing ended after switching tracks does not re-emit for the stale narration", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const events: Array<{ sourceId: string }> = [];
    const emit: SliceEmitter = (sourceId) => events.push({ sourceId });

    controller.play(narration("one"), "/one.mp3", emit);
    controller.play(narration("two"), "/two.mp3", emit);
    engine.fireEnded();

    expect(events).toEqual([{ sourceId: "two" }]);
  });

  it("pause(id) is a no-op for a stale/other narration id, and acts when the id matches (P2-04 target semantics)", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const emit: SliceEmitter = () => {};

    controller.play(narration("one"), "/one.mp3", emit);
    engine.calls.length = 0; // ignore the initial play() call

    controller.pause("stale-id");
    expect(engine.calls).toEqual([]);

    controller.pause("one");
    expect(engine.calls).toEqual([{ op: "pause" }]);
  });

  it("stop(id) is a no-op for a stale/other narration id, and acts when the id matches (P2-04 target semantics)", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const emit: SliceEmitter = () => {};

    controller.play(narration("one"), "/one.mp3", emit);
    engine.calls.length = 0; // ignore the initial play() call

    controller.stop("stale-id");
    expect(engine.calls).toEqual([]);
    expect(controller.getSnapshot()?.id).toBe("one"); // still active — never stopped

    controller.stop("one");
    expect(engine.calls.every((c) => c.op === "stop")).toBe(true); // acted (detach() also stops the engine)
    expect(controller.getSnapshot()).toBeNull();
  });

  it("pause()/stop() with no id (manual transport controls) always act on whichever track is active", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const emit: SliceEmitter = () => {};

    controller.play(narration("one"), "/one.mp3", emit);
    engine.calls.length = 0;

    controller.pause();
    expect(engine.calls).toEqual([{ op: "pause" }]);

    controller.stop();
    expect(engine.calls.slice(-1)).toEqual([{ op: "stop" }]);
  });

  it("surfaces a rejected play() as a blocked status instead of hanging, without throwing", async () => {
    const engine = new FakeAudioEngine();
    engine.rejectNextPlay = new Error("autoplay blocked");
    const controller = new NarrationController(engine);
    const emit: SliceEmitter = () => {};

    controller.play(narration("one"), "/one.mp3", emit);
    expect(controller.getSnapshot()?.status).toBe("playing");

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(controller.getSnapshot()?.status).toBe("blocked");

    // retryBlocked() (the fallback control) can recover it.
    controller.retryBlocked();
    expect(controller.getSnapshot()?.status).toBe("playing");
  });

  // P1-09/D3: narration is priority 1 (highest) in the cross-block
  // single-audible-source arbiter — starting a track must preempt any
  // currently-registered video/HTML-music source.
  describe("audio arbiter (P1-09/D3)", () => {
    it("play() registers as the arbiter's 'narration' source and pauses lower-priority sources", () => {
      const engine = new FakeAudioEngine();
      const arbiter = new AudioArbiter();
      const controller = new NarrationController(engine, arbiter);
      const emit: SliceEmitter = () => {};
      let videoPaused = false;
      arbiter.notifyPlaying("video", "v1", () => (videoPaused = true));

      controller.play(narration("intro"), "/resolved/audio/intro.mp3", emit);

      expect(videoPaused).toBe(true);
    });

    it("a lower-priority source starting later is immediately paused too", () => {
      const engine = new FakeAudioEngine();
      const arbiter = new AudioArbiter();
      const controller = new NarrationController(engine, arbiter);
      const emit: SliceEmitter = () => {};

      controller.play(narration("intro"), "/resolved/audio/intro.mp3", emit);
      let htmlMusicPaused = false;
      arbiter.notifyPlaying("htmlMusic", "h1", () => (htmlMusicPaused = true));

      // htmlMusic is lower priority than the already-registered narration —
      // its own notifyPlaying call does not touch narration, but a fresh
      // narration.notifyPlaying (e.g. a subsequent play()) would pause it.
      controller.play(narration("two"), "/resolved/audio/two.mp3", emit);
      expect(htmlMusicPaused).toBe(true);
    });
  });

  it("renders the active narration transcript", () => {
    const engine = new FakeAudioEngine();
    const controller = new NarrationController(engine);
    const emit: SliceEmitter = () => {};
    render(<NarrationPlayer controller={controller} emit={emit} />);

    // nothing before a track starts
    expect(screen.queryByLabelText("讲解")).toBeNull();

    act(() => controller.play(narration("intro"), "/resolved/audio/intro.mp3", emit));
    expect(screen.getByText("transcript for intro")).toBeInTheDocument();
  });
});
