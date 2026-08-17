import type { RuntimeSceneResult } from "@mind-imprint/course-contract";
import type { AssetResolver } from "@mind-imprint/course-runtime";
import { useAudioEngine } from "../narration/audioEngine";
import { resolveSceneAudioUrl, useSceneAudio } from "./sceneAudio";

/** The fixed opening start-action label (§6.1). */
export const OPENING_START_LABEL = "一起开始吧";

export interface OpeningSceneProps {
  scene: RuntimeSceneResult;
  title: string;
  estimatedMinutes: number;
  objectives: string[];
  learningPreview: string[];
  /** Resolves `scene.audioUrl` when it is a raw relative asset key (§P2-04). */
  assetResolver: AssetResolver;
  onStart: () => void;
}

/**
 * §6.1 / §17.3 — presentational opening: greeting (the prepared/generated scene
 * text), the course title + estimate + learning preview + objectives, and the
 * single fixed start action. Carries no generation logic; it renders a
 * {@link RuntimeSceneResult} the CoursePlayer obtained from the opening
 * generator (fallback in this slice). Plays `scene.audioUrl` through the
 * injected AudioEngine on mount, falling back to a one-click "播放" control
 * if autoplay is blocked (§P2-04) — this never blocks the start action.
 */
export function OpeningScene({ scene, title, estimatedMinutes, objectives, learningPreview, assetResolver, onStart }: OpeningSceneProps) {
  const engine = useAudioEngine();
  const audioUrl = resolveSceneAudioUrl(assetResolver, scene.audioUrl);
  const audio = useSceneAudio(engine, audioUrl);

  return (
    <section className="course-opening" aria-label="课程开场" data-fallback={scene.fallbackUsed ? "true" : undefined}>
      <div className="course-opening__panel">
        <p className="course-opening__eyebrow">开始学习</p>
        <h1 className="course-opening__title">{title}</h1>
        <p className="course-opening__greeting">{scene.text}</p>
        <p className="course-opening__estimate">预计 {estimatedMinutes} 分钟</p>
        {learningPreview.length > 0 ? (
          <ul className="course-opening__preview">
            {learningPreview.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : null}
        {objectives.length > 0 ? (
          <>
            <h2 className="course-opening__objectives-heading">学习目标</h2>
            <ul className="course-opening__objectives" aria-label="学习目标">
              {objectives.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </>
        ) : null}
        <div className="course-opening__actions">
          {audio.status === "blocked" ? (
            <button type="button" className="course-opening__play-audio" data-audio-fallback="true" onClick={audio.start}>
              播放
            </button>
          ) : null}
          <button type="button" className="course-opening__start" onClick={onStart}>
            {OPENING_START_LABEL}
          </button>
        </div>
      </div>
    </section>
  );
}
