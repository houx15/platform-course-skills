import { createContext, useContext } from "react";

/**
 * §P1-09 / D3 — a single-audible-source arbiter across narration, video, and
 * interactive-HTML-authored music. Priority is fixed: narration > video >
 * HTML music. When a source starts (or is confirmed) playing, every
 * currently-registered LOWER-priority source is paused (its registered
 * `pause` callback invoked) and unregistered. This is basic "pause the
 * others", not full ducking (future — see the Slice 7 plan).
 *
 * A source registers under a stable `(kind, id)` key for as long as it is
 * the audible occupant of its priority level, and clears its own
 * registration (`notifyStopped`) when it stops on its own (learner pause,
 * natural end, hide/disable/unmount) — so a later `notifyPlaying` from
 * another source never tries to pause something already silent.
 */
export type AudioSourceKind = "narration" | "video" | "htmlMusic";

/** Lower index = higher priority. */
const PRIORITY_ORDER: readonly AudioSourceKind[] = ["narration", "video", "htmlMusic"];

function priorityOf(kind: AudioSourceKind): number {
  return PRIORITY_ORDER.indexOf(kind);
}

interface RegisteredSource {
  kind: AudioSourceKind;
  pause: () => void;
}

export class AudioArbiter {
  private readonly playing = new Map<string, RegisteredSource>();

  private key(kind: AudioSourceKind, id: string): string {
    return `${kind}:${id}`;
  }

  /**
   * Registers `(kind, id)` as currently audible, with `pause` as the
   * callback the arbiter invokes to silence it later, then pauses AND
   * unregisters every already-registered source whose priority is LOWER
   * than `kind`'s (i.e. every source that must yield to this one).
   */
  notifyPlaying(kind: AudioSourceKind, id: string, pause: () => void): void {
    const myKey = this.key(kind, id);
    this.playing.set(myKey, { kind, pause });
    const myPriority = priorityOf(kind);
    for (const [key, source] of this.playing) {
      if (key === myKey) continue;
      if (priorityOf(source.kind) > myPriority) {
        source.pause();
        this.playing.delete(key);
      }
    }
  }

  /** Clears `(kind, id)`'s registration — it is no longer audible/eligible to be paused later. */
  notifyStopped(kind: AudioSourceKind, id: string): void {
    this.playing.delete(this.key(kind, id));
  }
}

/** Module-level default so every consumer without a provider shares one arbiter. */
let defaultArbiter: AudioArbiter | null = null;
export function getDefaultAudioArbiter(): AudioArbiter {
  if (!defaultArbiter) defaultArbiter = new AudioArbiter();
  return defaultArbiter;
}

const AudioArbiterContext = createContext<AudioArbiter | null>(null);

export const AudioArbiterProvider = AudioArbiterContext.Provider;

/** Reads the injected arbiter, falling back to the shared default instance. */
export function useAudioArbiter(): AudioArbiter {
  return useContext(AudioArbiterContext) ?? getDefaultAudioArbiter();
}
