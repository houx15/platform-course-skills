import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BlockRendererProps, InteractiveHtmlBlock } from "../types";
import type { InteractionCompletedPayload, SliceEmitter } from "@mind-imprint/course-runtime";
import { PROTOCOL_NAME, PROTOCOL_VERSION, buildHostMessage, parseFrameMessage, type HostMessageType } from "./protocol";
import { useAudioArbiter } from "../../media/audioArbiter";

/**
 * §9.5 / §17.11 / §20 / P1-09(D3) — the sandboxed-iframe boundary for
 * `interactiveHtml` blocks. This is the ONLY place course-authored code
 * runs, so it is the tightest trust boundary in the runtime.
 *
 * The renderer loads one self-contained HTML file into a `sandbox="allow-scripts"`
 * iframe — scripts only, NO `allow-same-origin` (so the frame has an opaque
 * origin and cannot reach app cookies/storage), no forms/popups/top-navigation.
 * It mints a per-mount `sessionToken`, posts a handshake on load so the frame
 * echoes the token, and accepts a message ONLY after validating the source
 * Window, protocol name, version, session token, and known `type`. Everything
 * else is dropped (optionally surfaced via `onRejected`) — never an Event.
 *
 * P1-09/D3 additions layered on top:
 * - A host→frame lifecycle (`activate`/`deactivate`/`enable`/`disable`/
 *   `pauseMedia`/`resumeMedia`/`stopMedia`, {@link buildHostMessage}) is
 *   posted on the block's visible/enabled transitions and on unmount.
 *   Authored HTML MAY cooperate by pausing its own audio, but the host does
 *   NOT depend on that cooperation for `enabled=false` (below).
 * - The iframe is granted `allow="autoplay"` ONLY when the block declares
 *   `capabilities.audio`. If the frame reports it couldn't start audio (an
 *   `error` message with `code: "autoplay-blocked"`), a visible one-click
 *   "开始音频" fallback appears; the learner's gesture posts `resumeMedia` —
 *   the workflow never deadlocks waiting on audio.
 * - `enabled=false` is enforced host-side, not merely announced: the frame
 *   is taken out of the pointer/tab-focus path (`pointer-events:none` +
 *   `tabIndex={-1}`) AND a capturing overlay sits over it, in addition to
 *   posting `disable`.
 * - A small cross-block audio arbiter (`../../media/audioArbiter`) is used
 *   so this frame's music yields (via `pauseMedia`) to narration or video —
 *   priority narration > video > HTML music (basic pause, not ducking).
 */

interface HtmlMessageHandlerDeps {
  /** Returns the frame's `contentWindow`; a message's `source` must equal this. */
  getExpectedSource: () => Window | null;
  /** The per-mount minted token; the frame must echo it back. */
  sessionToken: string;
  block: InteractiveHtmlBlock;
  emit: SliceEmitter;
  /** Diagnostics-only sink for rejected messages. Default no-op at the callsite. */
  onRejected: (reason: string) => void;
  /** Fired once, after a valid completion under `interaction-complete`. */
  onCompleted?: () => void;
  /**
   * P1-09 — fired for a valid `error` message carrying `code:
   * "autoplay-blocked"`, the convention the frame uses to report that its
   * declared audio failed to start under the browser's autoplay policy.
   */
  onAutoplayBlocked?: () => void;
}

/**
 * Pure factory for the `(data, source)` message handler. Kept independent of the
 * `window` 'message' listener (which is a thin adapter passing `event.data,
 * event.source`) so every acceptance/rejection predicate is unit-testable —
 * jsdom cannot freely set `MessageEvent.source`, so we test this directly.
 *
 * Every predicate must pass or the message is DROPPED: `source` Window, then
 * protocol/version/token/type/payload via {@link parseFrameMessage} — a
 * `completed` message with no learning evidence is rejected there (reason
 * `"payload"`) and never reaches this handler's completion path at all.
 *
 * A valid `ready`/`progress`/`error` becomes `interaction.<type>` verbatim. A
 * valid `completed` is handled specially (P1-08): it is re-shaped into the
 * typed `InteractionCompletedPayload` the Slice-1 `sessionState` reducer
 * expects — `{ interactionId, result: { correct, value } }` — with
 * `interactionId` ALWAYS the block id (host-stamped, never the frame's own
 * `resultId`, matching the video-cue identity convention) — and emitted as
 * `interaction.completed`; only then, and only when the block's completion
 * rule is `interaction-complete`, does it additionally emit `block.completed`.
 * A duplicate `completed` (this mount already completed once) is dropped
 * entirely — no re-validation, no re-emit of either event — making
 * completion idempotent per mount.
 */
export function createHtmlMessageHandler(deps: HtmlMessageHandlerDeps): (data: unknown, source: unknown) => void {
  let completed = false;
  return (data, source) => {
    if (source !== deps.getExpectedSource()) {
      deps.onRejected("source");
      return;
    }
    const result = parseFrameMessage(data, {
      sessionToken: deps.sessionToken,
      expectedVersion: deps.block.protocolVersion,
    });
    if (!result.ok) {
      deps.onRejected(result.reason);
      return;
    }

    if (result.type === "completed") {
      if (completed) return; // idempotent: a resent/duplicate completed message is silently dropped
      completed = true;
      const payload: InteractionCompletedPayload = {
        interactionId: deps.block.id,
        result: { correct: result.payload.correct, value: result.payload.value },
      };
      deps.emit(deps.block.id, "interaction.completed", payload);
      if (deps.block.completion?.rule === "interaction-complete") {
        deps.emit(deps.block.id, "block.completed");
        deps.onCompleted?.();
      }
      return;
    }

    if (result.type === "error" && result.payload.code === "autoplay-blocked") {
      deps.onAutoplayBlocked?.();
    }

    deps.emit(deps.block.id, `interaction.${result.type}`, result.payload);
  };
}

const ASPECT_CSS: Record<InteractiveHtmlBlock["aspectRatio"], string> = {
  "1:1": "1 / 1",
  "4:3": "4 / 3",
};

const defaultTokenFactory = (): string => globalThis.crypto.randomUUID();

export interface HtmlInteractionRendererProps extends BlockRendererProps<InteractiveHtmlBlock> {
  /** Injected for determinism; default mints a random per-mount token. */
  tokenFactory?: () => string;
  /** Diagnostics sink for dropped messages; default no-op. */
  onRejected?: (reason: string) => void;
}

export const HtmlInteractionRenderer = ({
  block,
  assetResolver,
  visible,
  enabled,
  emit,
  tokenFactory = defaultTokenFactory,
  onRejected = () => {},
}: HtmlInteractionRendererProps) => {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const arbiter = useAudioArbiter();
  const hasAudio = block.capabilities?.audio === true;

  // Mint the token once per mount; a re-mount (new instance) mints a new token,
  // so tokens from a previous mount are dead.
  const sessionTokenRef = useRef<string | undefined>(undefined);
  if (sessionTokenRef.current === undefined) sessionTokenRef.current = tokenFactory();
  const sessionToken = sessionTokenRef.current;

  // P1-11 — the iframe `src` is captured ONCE at mount, not recomputed inline
  // from `assetResolver.resolve()` on every render. A signed-URL refresh
  // re-renders the whole tree; reloading an ACTIVE interactive-HTML frame on
  // an unrelated background refresh would destroy the interaction's internal
  // JS state (its own DOM/variables live inside the sandboxed document, which
  // a `src` change tears down and reloads from scratch). The src only
  // changes on an explicit load error (below) — and even then only if the
  // resolver actually returns something different.
  const [frameSrc, setFrameSrc] = useState(() => assetResolver.resolve(block.source));
  const frameSrcRef = useRef(frameSrc);
  frameSrcRef.current = frameSrc;

  // Latest emit/onRejected for the mount-stable handler.
  const emitRef = useRef(emit);
  emitRef.current = emit;
  const onRejectedRef = useRef(onRejected);
  onRejectedRef.current = onRejected;

  // P1-09 — the frame reported it couldn't start its declared audio (`error`
  // with `code: "autoplay-blocked"`). The learner recovers via the "开始音频"
  // fallback below, which posts `resumeMedia` on their gesture — the
  // workflow never hangs silently waiting for HTML audio to start.
  const [audioFallback, setAudioFallback] = useState(false);

  // Host→frame lifecycle (P1-09/D3): only posted once the frame has actually
  // loaded (and so had the chance to attach its own message listener) —
  // posting earlier would silently lose the message, not queue it. The
  // frame's `contentWindow` is captured ONCE at load time (not re-read from
  // `iframeRef.current` on every post) so an unmount-time post (`stopMedia`)
  // still works even if React has already detached the iframe ref by the
  // time this cleanup effect runs.
  const loadedRef = useRef(false);
  const frameWindowRef = useRef<Window | null>(null);
  const postHostMessage = useCallback(
    (type: HostMessageType) => {
      const win = frameWindowRef.current;
      if (!win || !loadedRef.current) return;
      win.postMessage(buildHostMessage(type, sessionToken), "*");
    },
    [sessionToken],
  );

  const handleMessage = useMemo(
    () =>
      createHtmlMessageHandler({
        getExpectedSource: () => iframeRef.current?.contentWindow ?? null,
        sessionToken,
        block,
        emit: (sourceId, type, payload) => emitRef.current(sourceId, type, payload),
        onRejected: (reason) => onRejectedRef.current(reason),
        onAutoplayBlocked: () => {
          if (hasAudio) setAudioFallback(true);
        },
      }),
    [sessionToken, block, hasAudio],
  );

  useEffect(() => {
    const listener = (event: MessageEvent) => handleMessage(event.data, event.source);
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [handleMessage]);

  // P1-11 — an explicit load error is the ONE case that re-resolves the src
  // (recovering from an expired URL is worth the reload; an unrelated
  // background refresh is not). React does not wire a delegated `onError`
  // for `<iframe>` — only `onLoad` (confirmed in PdfRenderer, Slice 6 Task 1)
  // — so the native `error` event is bound directly on the element.
  useEffect(() => {
    const el = iframeRef.current;
    if (!el) return;
    const handleError = () => {
      const fresh = assetResolver.resolve(block.source);
      if (fresh !== frameSrcRef.current) setFrameSrc(fresh);
    };
    el.addEventListener("error", handleError);
    return () => el.removeEventListener("error", handleError);
  }, [assetResolver, block.source]);

  // P1-09 — mirror visible/enabled to the frame on every transition. The
  // very first run (pre-load) is a guaranteed no-op via `postHostMessage`'s
  // `loadedRef` guard; `handleLoad` below re-sends the CURRENT state once
  // the frame has actually loaded, so nothing is lost.
  useEffect(() => {
    postHostMessage(visible ? "activate" : "deactivate");
    if (!visible) postHostMessage("pauseMedia");
  }, [visible, postHostMessage]);

  useEffect(() => {
    postHostMessage(enabled ? "enable" : "disable");
    if (!enabled) postHostMessage("pauseMedia");
  }, [enabled, postHostMessage]);

  // P1-09 — an active (visible+enabled), audio-capable block occupies the
  // "htmlMusic" priority slot in the cross-block arbiter: narration or video
  // starting will pause it (posting `pauseMedia`) through this callback.
  // Unregisters on hide/disable/unmount so a later higher-priority start
  // never tries to pause a frame no longer eligible to be audible.
  useEffect(() => {
    if (!hasAudio || !visible || !enabled) return;
    arbiter.notifyPlaying("htmlMusic", block.id, () => postHostMessage("pauseMedia"));
    return () => arbiter.notifyStopped("htmlMusic", block.id);
  }, [arbiter, hasAudio, visible, enabled, block.id, postHostMessage]);

  // P1-09 — leaving the slice (unmount) stops HTML media outright, whatever
  // the last visible/enabled state was.
  useEffect(() => {
    return () => postHostMessage("stopMedia");
  }, [postHostMessage]);

  const handleLoad = () => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    // Handshake: the frame is opaque-origin, so targetOrigin must be "*". The
    // message carries only the token (no secrets) so the frame can echo it back.
    win.postMessage({ protocol: PROTOCOL_NAME, version: PROTOCOL_VERSION, sessionToken }, "*");
    frameWindowRef.current = win;
    loadedRef.current = true;
    // Sync the frame to the CURRENT lifecycle state — load can complete after
    // visible/enabled already changed (e.g. an error-triggered src re-resolve).
    postHostMessage(visible ? "activate" : "deactivate");
    postHostMessage(enabled ? "enable" : "disable");
  };

  const handleStartAudio = () => {
    setAudioFallback(false);
    postHostMessage("resumeMedia");
  };

  return (
    <div
      data-block-id={block.id}
      data-block-type="interactiveHtml"
      data-aspect-ratio={block.aspectRatio}
      hidden={!visible}
      aria-hidden={!visible}
      aria-disabled={!enabled}
      className="course-block course-block--interactive-html"
      style={{ aspectRatio: ASPECT_CSS[block.aspectRatio], position: "relative" }}
    >
      <iframe
        ref={iframeRef}
        className="course-interactive-html__frame"
        title={`interactive-${block.id}`}
        // §20: scripts only — opaque origin, no same-origin/forms/popups/top-nav
        // and no network affordances. `allow="autoplay"` is granted ONLY when
        // the block declares an audio capability (P1-09) — never otherwise.
        sandbox="allow-scripts"
        allow={hasAudio ? "autoplay" : undefined}
        // P1-09 — `enabled=false` is REAL, not advisory: the frame is taken
        // out of the tab-focus order and pointer events don't reach it.
        tabIndex={enabled ? undefined : -1}
        src={frameSrc}
        onLoad={handleLoad}
        style={{ width: "100%", height: "100%", border: "0", pointerEvents: enabled ? "auto" : "none" }}
      />
      {!enabled ? (
        // P1-09 — a capturing overlay over the entire frame, redundant with
        // (but not reliant on) the iframe's own `pointer-events:none` above —
        // belt-and-suspenders so disabled interaction truly cannot be reached.
        <div
          className="course-interactive-html__disabled-overlay"
          data-testid="html-disabled-overlay"
          aria-hidden="true"
          style={{ position: "absolute", inset: 0 }}
        />
      ) : null}
      {hasAudio && audioFallback ? (
        <button type="button" className="course-interactive-html__audio-fallback" onClick={handleStartAudio}>
          开始音频
        </button>
      ) : null}
    </div>
  );
};
