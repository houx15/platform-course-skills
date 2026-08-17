import { createContext, useContext, useRef } from "react";

/**
 * §17.10 — the minimal media surface {@link VideoRenderer} and the cue timeline
 * need. Injected so tests (and non-DOM hosts) can substitute a deterministic
 * fake: jsdom does not implement `HTMLMediaElement` playback, so all timing is
 * driven through the engine's reported `currentTime`, never the wall clock.
 */
export interface VideoEngine {
  play(): void;
  pause(): void;
  /** Rewind to the start and stop. */
  reset(): void;
  /** The engine's reported playback position, in seconds. */
  currentTime(): number;
  /** Seek to `seconds`. */
  seek(seconds: number): void;
  /** Registers a time-update listener (called with the new currentTime); returns an unsubscribe fn. */
  onTimeUpdate(cb: (seconds: number) => void): () => void;
  /** Registers an `ended` listener; returns an unsubscribe fn. */
  onEnded(cb: () => void): () => void;
  /**
   * P2-03 — the SOURCE OF TRUTH for "playback started", fired whenever the
   * underlying media actually starts playing: a workflow `playBlock` effect, a
   * renderer button, AND the native `<video controls>` UI all route through
   * the same DOM `play` event, so this is the one place that unifies them
   * instead of only the renderer's own button handler observing itself.
   */
  onPlay(cb: () => void): () => void;
  /** The `onPlay` counterpart for "playback paused" (native controls included). */
  onPause(cb: () => void): () => void;
  /**
   * P2-03 — reports an autoplay-policy (or other) rejection of a `play()`
   * call, so the caller can surface a learner-recoverable affordance instead
   * of silently leaving the workflow waiting.
   */
  onPlayError(cb: (error: unknown) => void): () => void;
}

/**
 * Default engine: binds to the React-rendered `<video>` element via a getter, so
 * poster/captions/track live in the accessible DOM element while playback state
 * flows through this seam. The getter defers element access until after mount.
 */
export class HtmlVideoEngine implements VideoEngine {
  private readonly playErrorListeners = new Set<(error: unknown) => void>();

  constructor(private readonly getEl: () => HTMLVideoElement | null) {}

  play(): void {
    // `HTMLMediaElement.play()` returns a Promise that rejects on
    // autoplay-policy denial (or other playback failure) — not fatal to the
    // call itself, but MUST be surfaced (P2-03) rather than silently ignored.
    const result = this.getEl()?.play?.();
    if (result && typeof result.catch === "function") {
      result.catch((error: unknown) => {
        for (const cb of this.playErrorListeners) cb(error);
      });
    }
  }

  pause(): void {
    this.getEl()?.pause();
  }

  reset(): void {
    const el = this.getEl();
    if (el) {
      el.pause();
      el.currentTime = 0;
    }
  }

  currentTime(): number {
    return this.getEl()?.currentTime ?? 0;
  }

  seek(seconds: number): void {
    const el = this.getEl();
    if (el) el.currentTime = seconds;
  }

  onTimeUpdate(cb: (seconds: number) => void): () => void {
    const el = this.getEl();
    if (!el) return () => {};
    const handler = () => cb(el.currentTime);
    el.addEventListener("timeupdate", handler);
    return () => el.removeEventListener("timeupdate", handler);
  }

  onEnded(cb: () => void): () => void {
    const el = this.getEl();
    if (!el) return () => {};
    el.addEventListener("ended", cb);
    return () => el.removeEventListener("ended", cb);
  }

  onPlay(cb: () => void): () => void {
    const el = this.getEl();
    if (!el) return () => {};
    el.addEventListener("play", cb);
    return () => el.removeEventListener("play", cb);
  }

  onPause(cb: () => void): () => void {
    const el = this.getEl();
    if (!el) return () => {};
    el.addEventListener("pause", cb);
    return () => el.removeEventListener("pause", cb);
  }

  onPlayError(cb: (error: unknown) => void): () => void {
    this.playErrorListeners.add(cb);
    return () => this.playErrorListeners.delete(cb);
  }
}

/** A factory so each mounted video gets an engine bound to its own element. */
export type VideoEngineFactory = (getEl: () => HTMLVideoElement | null) => VideoEngine;

const VideoEngineContext = createContext<VideoEngineFactory | null>(null);

export const VideoEngineProvider = VideoEngineContext.Provider;

/**
 * Returns a stable {@link VideoEngine} for one mounted video, bound to `getEl`.
 * Uses the injected factory when a provider is present (tests inject a fake),
 * otherwise a per-instance {@link HtmlVideoEngine}. Created once per mount.
 */
export function useVideoEngine(getEl: () => HTMLVideoElement | null): VideoEngine {
  const factory = useContext(VideoEngineContext);
  const ref = useRef<VideoEngine | null>(null);
  if (ref.current === null) ref.current = factory ? factory(getEl) : new HtmlVideoEngine(getEl);
  return ref.current;
}
