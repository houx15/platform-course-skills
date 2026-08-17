import type { AudioEngine } from "../../src/narration/audioEngine";

/**
 * Deterministic {@link AudioEngine} for tests: records the call order and lets a
 * test fire `ended` synchronously. `calls` captures play/pause/stop in order so
 * single-track ordering (stop-before-play) can be asserted.
 */
export class FakeAudioEngine implements AudioEngine {
  readonly calls: Array<{ op: "play" | "pause" | "stop"; url?: string }> = [];
  private readonly endedListeners = new Set<() => void>();
  /**
   * When set, the NEXT `play()` call rejects with this error instead of
   * resolving (simulates a browser blocking autoplay). Consumed once, so a
   * retried `play()` (the fallback control) can succeed.
   */
  rejectNextPlay: Error | null = null;

  play(url: string): Promise<void> {
    this.calls.push({ op: "play", url });
    if (this.rejectNextPlay) {
      const error = this.rejectNextPlay;
      this.rejectNextPlay = null;
      return Promise.reject(error);
    }
    return Promise.resolve();
  }

  pause(): void {
    this.calls.push({ op: "pause" });
  }

  stop(): void {
    this.calls.push({ op: "stop" });
  }

  onEnded(cb: () => void): () => void {
    this.endedListeners.add(cb);
    return () => {
      this.endedListeners.delete(cb);
    };
  }

  /** Fires `ended` to every currently-registered listener. */
  fireEnded(): void {
    for (const listener of this.endedListeners) listener();
  }
}
