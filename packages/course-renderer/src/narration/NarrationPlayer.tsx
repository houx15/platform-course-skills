import { useSyncExternalStore } from "react";
import type { NarrationDefinition } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";
import type { AudioEngine } from "./audioEngine";
import { type AudioArbiter, getDefaultAudioArbiter } from "../media/audioArbiter";

/** The narration currently mounted in the player (post asset-resolution). */
export interface ActiveNarration {
  id: string;
  text: string;
  audioUrl: string;
  /**
   * `"blocked"` when the engine's `play()` rejected (autoplay policy / no
   * user gesture yet) — `narration.ended` will never fire until the learner
   * retries via {@link NarrationController.retryBlocked}. Never hangs the
   * workflow silently: the transcript and controls stay visible either way.
   */
  status: "playing" | "blocked";
}

/**
 * §11 / §17.13 — drives one {@link AudioEngine} on behalf of the SlicePlayer.
 * Enforces single-track playback (a new `play` stops the previous track first)
 * and emits `narration.ended` (sourced by the narration id) when the engine
 * reports the track finished. Framework-agnostic: exposes a `subscribe`/
 * `getSnapshot` pair so {@link NarrationPlayer} can render via
 * `useSyncExternalStore`.
 *
 * P1-09/D3: narration is the HIGHEST priority in the cross-block
 * {@link AudioArbiter} — starting a track registers it there so any
 * currently-playing video or interactive-HTML music is paused.
 */
export class NarrationController {
  private readonly engine: AudioEngine;
  private readonly arbiter: AudioArbiter;
  private readonly listeners = new Set<() => void>();
  private active: ActiveNarration | null = null;
  private unsubEnded: (() => void) | null = null;

  constructor(engine: AudioEngine, arbiter: AudioArbiter = getDefaultAudioArbiter()) {
    this.engine = engine;
    this.arbiter = arbiter;
    this.subscribe = this.subscribe.bind(this);
    this.getSnapshot = this.getSnapshot.bind(this);
  }

  /** Starts a narration track, stopping any current one first (single-track). */
  play(narration: NarrationDefinition, audioUrl: string, emit: SliceEmitter): void {
    if (this.active) {
      // Release the OUTGOING track's arbiter registration before detaching —
      // otherwise switching tracks without an explicit stop() (the normal
      // single-track path) would leave one stale entry per track in the
      // arbiter's map for the life of the session.
      this.arbiter.notifyStopped("narration", this.active.id);
      this.detach();
    }
    this.active = { id: narration.id, text: narration.text, audioUrl, status: "playing" };
    this.arbiter.notifyPlaying("narration", narration.id, () => this.engine.pause());
    this.unsubEnded = this.engine.onEnded(() => {
      emit(narration.id, "narration.ended");
    });
    // A rejected play() (autoplay blocked) surfaces as `status: "blocked"`
    // instead of hanging silently — `narration.ended` genuinely won't fire
    // until the learner retries via `retryBlocked()` (P2-04 fail-safe).
    this.engine.play(audioUrl).catch(() => {
      if (this.active?.id === narration.id) {
        this.active = { ...this.active, status: "blocked" };
        this.notify();
      }
    });
    this.notify();
  }

  /** Pauses the active track — only when `narrationId` is unset or matches it (§P2-04 target semantics: never act on a stale/other track). */
  pause(narrationId?: string): void {
    if (narrationId !== undefined && this.active?.id !== narrationId) return;
    this.engine.pause();
  }

  /** Stops the active track — only when `narrationId` is unset or matches it (§P2-04 target semantics: never act on a stale/other track). */
  stop(narrationId?: string): void {
    if (narrationId !== undefined && this.active?.id !== narrationId) return;
    const id = this.active?.id;
    this.engine.stop();
    this.detach();
    if (id !== undefined) this.arbiter.notifyStopped("narration", id);
    this.active = null;
    this.notify();
  }

  /** Replays the active track from the start (§11 replay control). */
  replay(emit: SliceEmitter): void {
    if (this.active) this.play({ id: this.active.id, text: this.active.text, audio: "" }, this.active.audioUrl, emit);
  }

  /** Retries a `"blocked"` track from a real user gesture (the fallback "播放" control). */
  retryBlocked(): void {
    if (!this.active || this.active.status !== "blocked") return;
    const { id, audioUrl } = this.active;
    this.engine.play(audioUrl).catch(() => {
      if (this.active?.id === id) {
        this.active = { ...this.active, status: "blocked" };
        this.notify();
      }
    });
    this.active = { ...this.active, status: "playing" };
    this.notify();
  }

  private detach(): void {
    this.engine.stop();
    this.unsubEnded?.();
    this.unsubEnded = null;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  getSnapshot(): ActiveNarration | null {
    return this.active;
  }

  private notify(): void {
    for (const listener of this.listeners) listener();
  }
}

export interface NarrationPlayerProps {
  controller: NarrationController;
  /** Slice-scoped emitter, used by the manual replay/pause/stop controls. */
  emit: SliceEmitter;
}

/**
 * Renders the accessible transcript + transport controls for the currently
 * active narration. Renders nothing when no narration is playing. Only one
 * narration is ever active (the controller guarantees single-track).
 */
export function NarrationPlayer({ controller, emit }: NarrationPlayerProps) {
  const active = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  if (!active) return null;
  return (
    <section className="course-narration" data-narration-id={active.id} data-narration-status={active.status} aria-label="讲解">
      {active.status === "blocked" ? (
        <button type="button" className="course-narration__play-fallback" data-narration-control="retry" onClick={() => controller.retryBlocked()}>
          播放
        </button>
      ) : null}
      <div className="course-narration__controls">
        <button type="button" className="course-narration__control" data-narration-control="replay" aria-label="重播" title="重播" onClick={() => controller.replay(emit)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 2v6h6" />
            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L3 8" />
          </svg>
        </button>
        <button type="button" className="course-narration__control" data-narration-control="pause" aria-label="暂停" title="暂停" onClick={() => controller.pause()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true">
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
          </svg>
        </button>
        <button type="button" className="course-narration__control" data-narration-control="stop" aria-label="停止" title="停止" onClick={() => controller.stop()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="1.5" />
          </svg>
        </button>
      </div>
      <p className="course-narration__transcript" data-narration-transcript>
        {active.text}
      </p>
    </section>
  );
}
