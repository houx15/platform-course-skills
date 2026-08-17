import type { RuntimeSceneResult } from "@mind-imprint/course-contract";
import type { AssetResolver } from "@mind-imprint/course-runtime";
import { useAudioEngine } from "../narration/audioEngine";
import { resolveSceneAudioUrl, useSceneAudio } from "./sceneAudio";

/** The fixed closing completion-action label (§6.2 / P1-03 completion policy). */
export const CLOSING_COMPLETE_LABEL = "完成课程";

export interface ClosingSceneProps {
  scene: RuntimeSceneResult;
  summary: string;
  takeaways: string[];
  transferApplications: string[];
  /** Resolves `scene.audioUrl` when it is a raw relative asset key (§P2-04). */
  assetResolver: AssetResolver;
  /**
   * Fires when the learner dismisses the Closing scene via the explicit
   * "完成课程" control — the ONLY completion policy this slice implements
   * (§P1-03). CoursePlayer marks the session `completed` and fires its own
   * `onComplete` prop from this callback; the scene never decides completion
   * on its own (e.g. never on narration end alone).
   */
  onComplete: () => void;
}

/**
 * §6.2 / §17.3 — presentational closing: the prepared/generated narration plus
 * the prepared summary, takeaways, and transfer applications, and the explicit
 * completion control. Purely presentational — the {@link RuntimeSceneResult}
 * comes from the closing generator (fallback in this slice). Plays
 * `scene.audioUrl` through the injected AudioEngine on mount, falling back to
 * a one-click "播放" control if autoplay is blocked (§P2-04) — this never
 * blocks the completion control.
 */
export function ClosingScene({ scene, summary, takeaways, transferApplications, assetResolver, onComplete }: ClosingSceneProps) {
  const engine = useAudioEngine();
  const audioUrl = resolveSceneAudioUrl(assetResolver, scene.audioUrl);
  const audio = useSceneAudio(engine, audioUrl);

  return (
    <section className="course-closing" aria-label="课程收尾" data-fallback={scene.fallbackUsed ? "true" : undefined}>
      <div className="course-closing__panel">
        <p className="course-closing__eyebrow">课程收尾</p>
        <p className="course-closing__narration">{scene.text}</p>
        {audio.status === "blocked" ? (
          <button type="button" className="course-closing__play-audio" data-audio-fallback="true" onClick={audio.start}>
            播放
          </button>
        ) : null}
        <h2 className="course-closing__summary-heading">小结</h2>
        <p className="course-closing__summary">{summary}</p>
        <h3 className="course-closing__takeaways-heading">要点</h3>
        <ul className="course-closing__takeaways">
          {takeaways.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
        <h3 className="course-closing__transfer-heading">迁移应用</h3>
        <ul className="course-closing__transfer">
          {transferApplications.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
        <div className="course-closing__actions">
          <button type="button" className="course-closing__complete" onClick={onComplete}>
            {CLOSING_COMPLETE_LABEL}
          </button>
        </div>
      </div>
    </section>
  );
}
