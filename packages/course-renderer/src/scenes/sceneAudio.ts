import { useEffect, useState } from "react";
import type { AssetResolver } from "@mind-imprint/course-runtime";
import type { AudioEngine } from "../narration/audioEngine";

/** Matches an absolute/protocol-relative URL or a site-rooted/data path — anything that does NOT need another pass through the AssetResolver. */
const ALREADY_RESOLVED_RE = /^(?:[a-z][a-z0-9+.-]*:)?\/\/|^\/|^data:/i;

/**
 * Resolves a scene's `RuntimeSceneResult.audioUrl` through the AssetResolver
 * only when it looks like a raw relative asset key rather than an
 * already-usable URL. The fallback path already resolves its `audio` key
 * before handing it to the generator (which commonly echoes it back
 * verbatim on fallback), and a real generator's synthesized speech is
 * typically an absolute (e.g. signed CDN) URL — both must pass through
 * unchanged; only a bare relative key gets resolved here.
 */
export function resolveSceneAudioUrl(assetResolver: AssetResolver, url: string | undefined): string | undefined {
  if (!url) return undefined;
  if (ALREADY_RESOLVED_RE.test(url)) return url;
  return assetResolver.resolve(url);
}

export type SceneAudioStatus = "idle" | "playing" | "blocked";

export interface SceneAudioState {
  status: SceneAudioStatus;
  /** (Re)starts playback — bound to the fallback "播放" control's onClick, which runs inside a real user gesture. */
  start: () => void;
}

/**
 * §6.1 / §6.2 / P2-04 — plays an Opening/Closing scene's audio once through
 * the injected {@link AudioEngine} when mounted. A `play()` rejection
 * (autoplay blocked before any user gesture) surfaces as `status: "blocked"`
 * — it is never thrown and the caller never awaits it, so a scene's render
 * (and the course phase) is never held up waiting on playback. The scene
 * renders a one-click "播放" fallback bound to `start()` while blocked.
 * Stops the engine on unmount so a scene's audio never bleeds into the next
 * phase (a later slice, or the other scene).
 */
export function useSceneAudio(engine: AudioEngine, audioUrl: string | undefined): SceneAudioState {
  const [status, setStatus] = useState<SceneAudioStatus>("idle");

  const start = () => {
    if (!audioUrl) return;
    setStatus("playing");
    engine.play(audioUrl).catch(() => setStatus("blocked"));
  };

  useEffect(() => {
    if (!audioUrl) {
      setStatus("idle");
      return;
    }
    start();
    return () => {
      engine.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl, engine]);

  return { status, start };
}
