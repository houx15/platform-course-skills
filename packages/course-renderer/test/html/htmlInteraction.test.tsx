import { act, fireEvent, render } from "@testing-library/react";
import type { BlockSessionState } from "@mind-imprint/course-contract";
import { applyEvent, initSliceState, type SliceEmitter } from "@mind-imprint/course-runtime";
import {
  HtmlInteractionRenderer,
  createHtmlMessageHandler,
} from "../../src/blocks/html/HtmlInteractionRenderer";
import { PROTOCOL_NAME, PROTOCOL_VERSION } from "../../src/blocks/html/protocol";
import type { InteractiveHtmlBlock } from "../../src/blocks/types";
import { AudioArbiter, AudioArbiterProvider } from "../../src/media/audioArbiter";

const assetResolver = { resolve: (p: string) => `/resolved/${p}` };
const baseState: BlockSessionState = { visible: true, enabled: true, completed: false };

const block: InteractiveHtmlBlock = {
  id: "h1",
  type: "interactiveHtml",
  source: "assets/interactions/sort.html",
  protocolVersion: "1.0",
  aspectRatio: "4:3",
  completion: { rule: "interaction-complete" },
};

/** Same block, declaring the P1-09 audio capability. */
const audioBlock: InteractiveHtmlBlock = {
  ...block,
  id: "h-audio",
  capabilities: { audio: true },
};

interface Recorded {
  sourceId: string;
  type: string;
  payload: unknown;
}

function recorder() {
  const events: Recorded[] = [];
  const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
  return { events, emit };
}

// A stub Window plays the role of `iframe.contentWindow` for the source check.
const frameWindow = {} as unknown as Window;

function frameMsg(overrides: Record<string, unknown> = {}) {
  return {
    protocol: PROTOCOL_NAME,
    version: PROTOCOL_VERSION,
    sessionToken: "fixed-tok",
    type: "ready",
    ...overrides,
  };
}

function makeHandler(over: Partial<Parameters<typeof createHtmlMessageHandler>[0]> = {}) {
  const { events, emit } = recorder();
  const rejected: string[] = [];
  const handler = createHtmlMessageHandler({
    getExpectedSource: () => frameWindow,
    sessionToken: "fixed-tok",
    block,
    emit,
    onRejected: (reason) => rejected.push(reason),
    ...over,
  });
  return { handler, events, rejected };
}

describe("HtmlInteractionRenderer (component)", () => {
  it("renders a sandboxed iframe (allow-scripts only, NO allow-same-origin) in an aspect-ratio wrapper", () => {
    const { emit } = recorder();
    const { container } = render(
      <HtmlInteractionRenderer
        block={block}
        assetResolver={assetResolver}
        state={baseState}
        visible
        enabled
        emit={emit}
        tokenFactory={() => "fixed-tok"}
      />,
    );
    const iframe = container.querySelector("iframe");
    expect(iframe).not.toBeNull();
    expect(iframe!.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe!.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(iframe!.getAttribute("src")).toBe("/resolved/assets/interactions/sort.html");

    const wrapper = container.querySelector('[data-block-type="interactiveHtml"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper!.getAttribute("data-aspect-ratio")).toBe("4:3");
  });

  it("publishes aspectRatio as a HINT only — never as a CSS clamp on the frame", () => {
    // Clamping the wrapper to the ratio cropped wide interactions to a narrow
    // column and pushed their own 完成 footer out of reach, which on an
    // `after-completion` slice left the student with no way to finish. The
    // ratio stays as a data attribute for styling; sizing comes from the slot.
    const { emit } = recorder();
    for (const aspectRatio of ["1:1", "4:3", "fill"] as const) {
      const { container } = render(
        <HtmlInteractionRenderer
          block={{ ...block, aspectRatio }}
          assetResolver={assetResolver}
          state={baseState}
          visible
          enabled
          emit={emit}
          tokenFactory={() => "fixed-tok"}
        />,
      );
      const wrapper = container.querySelector('[data-block-type="interactiveHtml"]') as HTMLElement;
      expect(wrapper.getAttribute("data-aspect-ratio")).toBe(aspectRatio);
      expect(wrapper.style.aspectRatio).toBe("");
    }
  });

  it("marks the block non-interactive when enabled=false (advisory; sandbox already isolates)", () => {
    const { emit } = recorder();
    const { container } = render(
      <HtmlInteractionRenderer
        block={block}
        assetResolver={assetResolver}
        state={{ ...baseState, enabled: false }}
        visible
        enabled={false}
        emit={emit}
        tokenFactory={() => "fixed-tok"}
      />,
    );
    const wrapper = container.querySelector('[data-block-type="interactiveHtml"]');
    expect(wrapper!.getAttribute("aria-disabled")).toBe("true");
  });

  // P1-11: a signed-URL refresh re-renders the whole course tree. Reloading
  // an ACTIVE interactive-HTML iframe on an unrelated background refresh
  // destroys the interaction's internal state (it lives inside the
  // sandboxed document, which a `src` change tears down).
  describe("URL-refresh safety (P1-11)", () => {
    it("does NOT reload the iframe on a background re-render — src stays stable", () => {
      const { emit } = recorder();
      let current = "/resolved/v1.html";
      const resolver = { resolve: () => current };
      // A FRESH element each call (not a cached, reused JSX reference) — a
      // real parent state update always produces new props objects for its
      // subtree, so reusing one element across `rerender()` would let React
      // bail via prop-identity and never actually re-invoke this component,
      // masking the exact bug P1-11 fixes.
      const buildUi = () => (
        <HtmlInteractionRenderer
          block={block}
          assetResolver={resolver}
          state={baseState}
          visible
          enabled
          emit={emit}
          tokenFactory={() => "fixed-tok"}
        />
      );
      const { container, rerender } = render(buildUi());
      const iframe = container.querySelector("iframe")!;
      expect(iframe).toHaveAttribute("src", "/resolved/v1.html");

      current = "/resolved/v2-renewed.html";
      rerender(buildUi()); // simulate RuntimeCoursePlayer's refresh-triggered re-render

      expect(iframe).toHaveAttribute("src", "/resolved/v1.html"); // stable — no reload
    });

    it("re-resolves the src on an explicit load error (recovering an expired URL)", () => {
      const { emit } = recorder();
      let current = "/resolved/v1.html";
      const resolver = { resolve: () => current };
      const { container } = render(
        <HtmlInteractionRenderer
          block={block}
          assetResolver={resolver}
          state={baseState}
          visible
          enabled
          emit={emit}
          tokenFactory={() => "fixed-tok"}
        />,
      );
      const iframe = container.querySelector("iframe")!;
      expect(iframe).toHaveAttribute("src", "/resolved/v1.html");

      current = "/resolved/v2-renewed.html";
      act(() => {
        iframe.dispatchEvent(new Event("error"));
      });

      expect(iframe).toHaveAttribute("src", "/resolved/v2-renewed.html");
    });
  });
});

describe("createHtmlMessageHandler (message boundary)", () => {
  it("emits interaction.ready for a valid ready message from the frame source", () => {
    const { handler, events, rejected } = makeHandler();
    handler(frameMsg({ type: "ready", payload: { step: 1 } }), frameWindow);
    expect(events).toEqual([{ sourceId: "h1", type: "interaction.ready", payload: { step: 1 } }]);
    expect(rejected).toEqual([]);
  });

  it("emits a typed interaction.completed then block.completed for a valid completed message (P1-08)", () => {
    const { handler, events } = makeHandler();
    handler(frameMsg({ type: "completed", payload: { correct: true, value: 3 } }), frameWindow);
    expect(events.map((e) => e.type)).toEqual(["interaction.completed", "block.completed"]);
    // interactionId is HOST-stamped (the block id), never trusted from the frame.
    expect(events[0]?.payload).toEqual({ interactionId: "h1", result: { correct: true, value: 3 } });
  });

  it("rejects a completed message with no learning evidence: no interaction.completed, no block.completed (P1-08)", () => {
    const { handler, events, rejected } = makeHandler();
    handler(frameMsg({ type: "completed", payload: {} }), frameWindow);
    expect(events).toEqual([]);
    expect(rejected).toEqual(["payload"]);
  });

  it("is idempotent: a duplicate completed message does not double-complete or double-emit (P1-08)", () => {
    const { handler, events } = makeHandler();
    handler(frameMsg({ type: "completed", payload: { correct: true } }), frameWindow);
    handler(frameMsg({ type: "completed", payload: { correct: true, value: "different-retry" } }), frameWindow);
    expect(events.filter((e) => e.type === "block.completed")).toHaveLength(1);
    expect(events.filter((e) => e.type === "interaction.completed")).toHaveLength(1);
  });

  it("does NOT emit block.completed when completion rule is absent, but still emits interaction.completed", () => {
    const noRule: InteractiveHtmlBlock = { ...block, completion: undefined };
    const { handler, events } = makeHandler({ block: noRule });
    handler(frameMsg({ type: "completed", payload: { value: "done" } }), frameWindow);
    expect(events.map((e) => e.type)).toEqual(["interaction.completed"]);
  });

  it("drops a wrong-token message: no emit, onRejected('token')", () => {
    const { handler, events, rejected } = makeHandler();
    handler(frameMsg({ type: "completed", payload: { correct: true }, sessionToken: "stale" }), frameWindow);
    expect(events).toEqual([]);
    expect(rejected).toEqual(["token"]);
  });

  it("drops a message whose source is not the iframe window: no emit", () => {
    const { handler, events, rejected } = makeHandler();
    const otherWindow = {} as unknown as Window;
    handler(frameMsg({ type: "completed", payload: { correct: true } }), otherWindow);
    expect(events).toEqual([]);
    expect(rejected).toEqual(["source"]);
  });

  it("calls onCompleted after a valid completion", () => {
    let done = false;
    const { handler } = makeHandler({ onCompleted: () => (done = true) });
    handler(frameMsg({ type: "completed", payload: { correct: true } }), frameWindow);
    expect(done).toBe(true);
  });

  it("calls onAutoplayBlocked for an error message carrying code 'autoplay-blocked' (P1-09), and still emits interaction.error", () => {
    let blocked = false;
    const { handler, events } = makeHandler({ onAutoplayBlocked: () => (blocked = true) });
    handler(frameMsg({ type: "error", payload: { message: "autoplay rejected", code: "autoplay-blocked" } }), frameWindow);
    expect(blocked).toBe(true);
    expect(events).toEqual([{ sourceId: "h1", type: "interaction.error", payload: { message: "autoplay rejected", code: "autoplay-blocked" } }]);
  });

  it("does NOT call onAutoplayBlocked for an error message with a different/no code", () => {
    let blocked = false;
    const { handler } = makeHandler({ onAutoplayBlocked: () => (blocked = true) });
    handler(frameMsg({ type: "error", payload: { message: "sandboxed script threw" } }), frameWindow);
    handler(frameMsg({ type: "error", payload: { message: "boom", code: "other" } }), frameWindow);
    expect(blocked).toBe(false);
  });

  it("emits interaction.progress and interaction.error for valid progress/error payloads", () => {
    const { handler, events, rejected } = makeHandler();
    handler(frameMsg({ type: "progress", payload: { step: 2 } }), frameWindow);
    handler(frameMsg({ type: "error", payload: { message: "sandboxed script threw" } }), frameWindow);
    expect(events).toEqual([
      { sourceId: "h1", type: "interaction.progress", payload: { step: 2 } },
      { sourceId: "h1", type: "interaction.error", payload: { message: "sandboxed script threw" } },
    ]);
    expect(rejected).toEqual([]);
  });

  it("round-trips a valid completion into course-runtime's interactionResult via applyEvent (P1-08)", () => {
    const { handler, events } = makeHandler();
    handler(frameMsg({ type: "completed", payload: { correct: true, value: 42 } }), frameWindow);

    const slice = { id: "s1", title: "s", blocks: [block], workflow: { initialState: undefined, steps: [] } } as unknown as Parameters<
      typeof initSliceState
    >[0];
    let sliceState = initSliceState(slice);
    for (const e of events) {
      sliceState = applyEvent(sliceState, { type: e.type, sourceId: e.sourceId, payload: e.payload });
    }
    expect(sliceState.blockStates["h1"]?.completed).toBe(true);
    expect(sliceState.blockStates["h1"]?.interactionResult).toEqual({ h1: { correct: true, value: 42 } });
  });
});

/**
 * P1-09 / D3 — host→frame lifecycle, autoplay gating/fallback, true
 * `enabled=false`, and the cross-block audio arbiter. jsdom DOES honor an
 * explicit `source` passed to the `MessageEvent` constructor (verified
 * against this jsdom version), so these tests dispatch real `window`
 * "message" events sourced from the rendered iframe's own `contentWindow` —
 * unlike a REAL cross-frame `postMessage`, which jsdom does not deliver
 * end-to-end for a `src`-less test iframe (that's the "cannot freely set"
 * limitation `createHtmlMessageHandler`'s own unit tests route around).
 */
describe("HtmlInteractionRenderer — host→frame lifecycle + audio (P1-09/D3)", () => {
  /** Extracts the `type` of every host→frame lifecycle message posted (skips the untyped session handshake). */
  function hostMessageTypes(spy: { mock: { calls: unknown[][] } }): string[] {
    return spy.mock.calls
      .map(([msg]) => msg as Record<string, unknown>)
      .filter((msg) => msg.protocol === PROTOCOL_NAME && typeof msg.type === "string")
      .map((msg) => msg.type as string);
  }

  it('grants allow="autoplay" only when the block declares capabilities.audio', () => {
    const { container: withoutAudio } = render(
      <HtmlInteractionRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={() => {}} tokenFactory={() => "t1"} />,
    );
    expect(withoutAudio.querySelector("iframe")!.getAttribute("allow")).toBeNull();

    const { container: withAudio } = render(
      <HtmlInteractionRenderer block={audioBlock} assetResolver={assetResolver} state={baseState} visible enabled emit={() => {}} tokenFactory={() => "t2"} />,
    );
    expect(withAudio.querySelector("iframe")!.getAttribute("allow")).toBe("autoplay");
  });

  it("posts activate+enable to the frame once loaded, then deactivate+pauseMedia when the block is hidden", () => {
    const emit: SliceEmitter = () => {};
    const buildUi = (visible: boolean, enabled: boolean) => (
      <HtmlInteractionRenderer block={block} assetResolver={assetResolver} state={baseState} visible={visible} enabled={enabled} emit={emit} tokenFactory={() => "fixed-tok"} />
    );
    const { container, rerender } = render(buildUi(true, true));
    const iframe = container.querySelector("iframe")!;
    const spy = vi.spyOn(iframe.contentWindow!, "postMessage");

    act(() => fireEvent.load(iframe));
    expect(hostMessageTypes(spy)).toEqual(["activate", "enable"]);

    spy.mockClear();
    rerender(buildUi(false, true));
    expect(hostMessageTypes(spy)).toEqual(["deactivate", "pauseMedia"]);
  });

  it("enabled=false truly blocks interaction (pointer-events:none + capturing overlay + no tab focus) and posts disable+pauseMedia; re-enabling clears it and posts enable", () => {
    const emit: SliceEmitter = () => {};
    const buildUi = (enabled: boolean) => (
      <HtmlInteractionRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled={enabled} emit={emit} tokenFactory={() => "fixed-tok"} />
    );
    const { container, rerender } = render(buildUi(true));
    const iframe = container.querySelector("iframe")!;
    const spy = vi.spyOn(iframe.contentWindow!, "postMessage");
    act(() => fireEvent.load(iframe));

    // Baseline: enabled — no overlay, pointer events reach the frame.
    expect(container.querySelector('[data-testid="html-disabled-overlay"]')).toBeNull();
    expect(iframe.style.pointerEvents).toBe("auto");
    expect(iframe.getAttribute("tabindex")).toBeNull();

    spy.mockClear();
    rerender(buildUi(false));
    expect(iframe.style.pointerEvents).toBe("none");
    expect(iframe.getAttribute("tabindex")).toBe("-1");
    expect(container.querySelector('[data-testid="html-disabled-overlay"]')).not.toBeNull();
    expect(hostMessageTypes(spy)).toEqual(["disable", "pauseMedia"]);

    spy.mockClear();
    rerender(buildUi(true));
    expect(iframe.style.pointerEvents).toBe("auto");
    expect(container.querySelector('[data-testid="html-disabled-overlay"]')).toBeNull();
    expect(hostMessageTypes(spy)).toEqual(["enable"]);
  });

  it("unmounting (leaving the slice) posts stopMedia", () => {
    const emit: SliceEmitter = () => {};
    const { container, unmount } = render(
      <HtmlInteractionRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} tokenFactory={() => "fixed-tok"} />,
    );
    const iframe = container.querySelector("iframe")!;
    const spy = vi.spyOn(iframe.contentWindow!, "postMessage");
    act(() => fireEvent.load(iframe));
    spy.mockClear();

    unmount();
    expect(hostMessageTypes(spy)).toEqual(["stopMedia"]);
  });

  describe("autoplay-blocked fallback", () => {
    function dispatchAutoplayBlocked(iframe: HTMLIFrameElement, sessionToken = "fixed-tok") {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            protocol: PROTOCOL_NAME,
            version: PROTOCOL_VERSION,
            sessionToken,
            type: "error",
            payload: { message: "autoplay rejected", code: "autoplay-blocked" },
          },
          source: iframe.contentWindow as unknown as Window,
        }),
      );
    }

    it("shows a one-click 开始音频 fallback when the frame reports autoplay-blocked, and the gesture posts resumeMedia — never deadlocks (P1-09)", () => {
      const emit: SliceEmitter = () => {};
      const { container } = render(
        <HtmlInteractionRenderer block={audioBlock} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} tokenFactory={() => "fixed-tok"} />,
      );
      const iframe = container.querySelector("iframe")!;
      const spy = vi.spyOn(iframe.contentWindow!, "postMessage");
      act(() => fireEvent.load(iframe));

      expect(container.querySelector(".course-interactive-html__audio-fallback")).toBeNull();

      act(() => dispatchAutoplayBlocked(iframe));

      const fallback = container.querySelector(".course-interactive-html__audio-fallback");
      expect(fallback).not.toBeNull();
      expect(fallback!.textContent).toBe("开始音频");

      spy.mockClear();
      act(() => fireEvent.click(fallback!));

      expect(hostMessageTypes(spy)).toEqual(["resumeMedia"]);
      expect(container.querySelector(".course-interactive-html__audio-fallback")).toBeNull();
    });

    it("never shows the audio fallback for a block that did not declare capabilities.audio", () => {
      const emit: SliceEmitter = () => {};
      const { container } = render(
        <HtmlInteractionRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} tokenFactory={() => "fixed-tok"} />,
      );
      const iframe = container.querySelector("iframe")!;
      act(() => fireEvent.load(iframe));

      act(() => dispatchAutoplayBlocked(iframe));

      expect(container.querySelector(".course-interactive-html__audio-fallback")).toBeNull();
    });
  });

  describe("single-audible-source arbiter", () => {
    it("registers an active audio-capable block as the arbiter's htmlMusic source; a higher-priority start pauses it via pauseMedia", () => {
      const arbiter = new AudioArbiter();
      const emit: SliceEmitter = () => {};
      const { container } = render(
        <AudioArbiterProvider value={arbiter}>
          <HtmlInteractionRenderer block={audioBlock} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} tokenFactory={() => "fixed-tok"} />
        </AudioArbiterProvider>,
      );
      const iframe = container.querySelector("iframe")!;
      const spy = vi.spyOn(iframe.contentWindow!, "postMessage");
      act(() => fireEvent.load(iframe));
      spy.mockClear();

      act(() => {
        arbiter.notifyPlaying("narration", "n1", () => {});
      });

      expect(hostMessageTypes(spy)).toEqual(["pauseMedia"]);
    });

    it("unregisters once hidden — a later higher-priority start does not post a stray pauseMedia", () => {
      const arbiter = new AudioArbiter();
      const emit: SliceEmitter = () => {};
      const buildUi = (visible: boolean) => (
        <AudioArbiterProvider value={arbiter}>
          <HtmlInteractionRenderer block={audioBlock} assetResolver={assetResolver} state={baseState} visible={visible} enabled emit={emit} tokenFactory={() => "fixed-tok"} />
        </AudioArbiterProvider>
      );
      const { container, rerender } = render(buildUi(true));
      const iframe = container.querySelector("iframe")!;
      const spy = vi.spyOn(iframe.contentWindow!, "postMessage");
      act(() => fireEvent.load(iframe));

      rerender(buildUi(false));
      spy.mockClear();
      act(() => arbiter.notifyPlaying("narration", "n1", () => {}));

      expect(hostMessageTypes(spy)).toEqual([]);
    });

    it("a non-audio-capable block never registers with the arbiter (no pauseMedia posted)", () => {
      const arbiter = new AudioArbiter();
      const emit: SliceEmitter = () => {};
      const { container } = render(
        <AudioArbiterProvider value={arbiter}>
          <HtmlInteractionRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} tokenFactory={() => "fixed-tok"} />
        </AudioArbiterProvider>,
      );
      const iframe = container.querySelector("iframe")!;
      const spy = vi.spyOn(iframe.contentWindow!, "postMessage");
      act(() => fireEvent.load(iframe));
      spy.mockClear();

      act(() => arbiter.notifyPlaying("video", "v1", () => {}));

      expect(hostMessageTypes(spy)).toEqual([]);
    });
  });
});
