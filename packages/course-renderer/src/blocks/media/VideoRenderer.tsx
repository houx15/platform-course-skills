import { useCallback, useEffect, useRef, useState } from "react";
import type { VideoPositionPayload } from "@mind-imprint/course-runtime";
import type { BlockRenderer, VideoBlock } from "../types";
import { useVideoEngine } from "../../media/videoEngine";
import { useMediaHandleRegistry } from "../../media/mediaRegistry";
import { useAudioArbiter } from "../../media/audioArbiter";
import { VideoInteractionController } from "./VideoInteractionController";

/**
 * §9.4 / §17.10 — the accessible video player. Renders a `<video>` (poster +
 * WebVTT caption track, resolved through the asset resolver) and drives playback
 * through the injectable {@link VideoEngine} seam so tests stay deterministic
 * under jsdom.
 *
 * The Slice Workflow treats the video as ONE component: the renderer registers a
 * media handle (`play`/`pause`/`reset`) so `playBlock`/`pauseBlock`/`resetBlock`
 * effects reach the element, emits `video.started`/`video.paused`/`video.ended`,
 * and emits `block.completed` only when its configured completion rule is met.
 * Under `video-ended-and-interactions-completed`, completion is gated on all
 * required timeline cues completing — reported up by {@link VideoInteractionController}.
 *
 * P2-03: `video.started`/`video.paused` are sourced from the engine's
 * `onPlay`/`onPause` — the native DOM `play`/`pause` events fire regardless of
 * WHO triggered playback (the custom buttons below, a workflow `playBlock`
 * effect via the media handle, or the learner using the native
 * `<video controls>` UI directly), so this is the single unified source
 * instead of only the button handlers observing themselves. `enabled` is
 * honored (hides native controls, disables the custom buttons); `reset` is
 * real (clears the video AND the cue controller's fired/completed/gate
 * state); a `play()` rejection (autoplay policy or otherwise) surfaces a
 * learner-recoverable retry affordance instead of leaving the workflow
 * silently stuck.
 */
export const VideoRenderer: BlockRenderer<VideoBlock> = ({ block, assetResolver, visible, enabled, emit }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const getEl = useCallback(() => videoRef.current, []);
  const engine = useVideoEngine(getEl);
  const registry = useMediaHandleRegistry();
  // P1-09/D3: video is priority 2 (below narration, above HTML music) in the
  // cross-block audio arbiter — starting playback pauses lower-priority
  // interactive-HTML music; a higher-priority narration start pauses this.
  const arbiter = useAudioArbiter();

  // Latest emit for the mount-once ended subscription.
  const emitRef = useRef(emit);
  emitRef.current = emit;

  // P1-11 — the video `src` is captured ONCE (the lazy `useState` initializer
  // runs only at mount) instead of being recomputed inline from
  // `assetResolver.resolve()` on every render. A signed-URL refresh
  // (RuntimeCoursePlayer re-signing before `expiresAt`) re-renders the whole
  // tree; if `src` were derived inline, an ACTIVE/playing video would reload
  // — resetting `currentTime` and dropping cue state — purely because an
  // unrelated background refresh happened elsewhere in the course. The src
  // only ever changes via `reresolveSrc`, called at a safe moment (a load
  // error, or a pause) and ONLY when the resolver actually returns something
  // different (i.e. a real refresh happened) — never a no-op swap.
  const [videoSrc, setVideoSrc] = useState(() => assetResolver.resolve(block.source));
  const videoSrcRef = useRef(videoSrc);
  videoSrcRef.current = videoSrc;
  // Position (+ whether to resume playback) to restore once a re-resolve swap lands.
  const pendingRestoreRef = useRef<{ time: number; resumePlay: boolean } | null>(null);
  const isPlayingRef = useRef(false);

  const reresolveSrc = useCallback(
    (resumePlay: boolean) => {
      const fresh = assetResolver.resolve(block.source);
      if (fresh === videoSrcRef.current) return; // resolver unchanged — no-op, no reload
      pendingRestoreRef.current = { time: engine.currentTime(), resumePlay };
      setVideoSrc(fresh);
    },
    [assetResolver, block.source, engine],
  );

  // After a re-resolve swaps `src`, restore the playback position (and resume
  // playback if it was mid-play when the swap happened).
  useEffect(() => {
    const pending = pendingRestoreRef.current;
    if (!pending) return;
    pendingRestoreRef.current = null;
    engine.seek(pending.time);
    if (pending.resumePlay) engine.play();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoSrc]);

  const gated = block.completion?.rule === "video-ended-and-interactions-completed";
  const videoEndedRef = useRef(false);
  const requiredCuesCompleteRef = useRef(!gated);
  const completedRef = useRef(false);
  const [cueResetSignal, setCueResetSignal] = useState(0);
  const [playError, setPlayError] = useState(false);

  const maybeComplete = useCallback(() => {
    if (completedRef.current) return;
    if (!videoEndedRef.current) return;
    if (gated && !requiredCuesCompleteRef.current) return;
    if (!block.completion) return;
    completedRef.current = true;
    emitRef.current(block.id, "block.completed");
  }, [block.completion, block.id, gated]);

  const play = useCallback(() => {
    if (!enabled) return;
    setPlayError(false);
    engine.play();
  }, [engine, enabled]);

  const pause = useCallback(() => {
    if (!enabled) return;
    engine.pause();
  }, [engine, enabled]);

  const reset = useCallback(() => {
    engine.reset();
    videoEndedRef.current = false;
    completedRef.current = false;
    requiredCuesCompleteRef.current = !gated;
    setPlayError(false);
    setCueResetSignal((n) => n + 1);
  }, [engine, gated]);

  // Register the media handle so play/pause/reset effects reach this element.
  useEffect(() => {
    if (!registry) return;
    return registry.register(block.id, { play, pause, reset });
  }, [registry, block.id, play, pause, reset]);

  // Native play/pause → the single source of `video.started`/`video.paused`.
  useEffect(() => {
    return engine.onPlay(() => {
      isPlayingRef.current = true;
      arbiter.notifyPlaying("video", block.id, () => engine.pause());
      emitRef.current(block.id, "video.started");
    });
  }, [engine, block.id, arbiter]);

  useEffect(() => {
    return engine.onPause(() => {
      isPlayingRef.current = false;
      arbiter.notifyStopped("video", block.id);
      const payload: VideoPositionPayload = { positionSeconds: engine.currentTime() };
      emitRef.current(block.id, "video.paused", payload);
      // P1-11: a pause is a SAFE moment to lazily pick up a renewed signed
      // URL — nothing is visibly playing, so a src swap (guarded as a no-op
      // when the resolver hasn't actually changed) can't interrupt playback.
      reresolveSrc(false);
    });
  }, [engine, block.id, reresolveSrc, arbiter]);

  // P1-11: a native load failure (e.g. the current URL 403'd after expiring)
  // is the other safe/necessary moment to re-resolve — recover by picking up
  // a renewed URL and resuming playback if it was mid-play when it failed.
  const handleMediaError = useCallback(() => {
    reresolveSrc(isPlayingRef.current);
  }, [reresolveSrc]);

  // Surface a play() rejection (e.g. autoplay policy) as a recoverable state
  // instead of leaving a gated workflow silently waiting for `video.started`.
  useEffect(() => {
    return engine.onPlayError(() => {
      setPlayError(true);
    });
  }, [engine]);

  // Subscribe to the engine's ended event.
  useEffect(() => {
    return engine.onEnded(() => {
      videoEndedRef.current = true;
      arbiter.notifyStopped("video", block.id);
      const payload: VideoPositionPayload = { positionSeconds: engine.currentTime() };
      emitRef.current(block.id, "video.ended", payload);
      maybeComplete();
    });
  }, [engine, block.id, maybeComplete, arbiter]);

  // The cue timeline reports when all required cues have completed (gated rule).
  const onRequiredCuesComplete = useCallback(() => {
    requiredCuesCompleteRef.current = true;
    maybeComplete();
  }, [maybeComplete]);

  return (
    <div
      data-block-id={block.id}
      data-block-type="video"
      hidden={!visible}
      aria-hidden={!visible}
      aria-disabled={!enabled}
      className="course-block course-block--video"
    >
      <video
        ref={videoRef}
        className="course-video__player"
        controls={enabled}
        tabIndex={enabled ? undefined : -1}
        src={videoSrc}
        poster={block.poster ? assetResolver.resolve(block.poster) : undefined}
        onError={handleMediaError}
      >
        {block.captions ? (
          <track kind="captions" src={assetResolver.resolve(block.captions)} default />
        ) : null}
      </video>
      {/* No custom play/pause buttons: the native <video controls> already
          provides the familiar player transport (play/volume/fullscreen).
          Workflow-driven play/pause still reaches the element via the media
          handle registered above; the only extra affordance is the recoverable
          autoplay-retry below. */}
      {playError ? (
        <p className="course-video__play-error" role="alert">
          播放未能开始，可能是浏览器阻止了自动播放。
          <button type="button" className="course-video__play-retry" onClick={play}>
            重试播放
          </button>
        </p>
      ) : null}
      {block.interaction ? (
        <VideoInteractionController
          block={block}
          engine={engine}
          assetResolver={assetResolver}
          emit={emit}
          onRequiredCuesComplete={onRequiredCuesComplete}
          visible={visible}
          resetSignal={cueResetSignal}
        />
      ) : null}
    </div>
  );
};
