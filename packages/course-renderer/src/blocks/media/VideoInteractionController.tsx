import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  validateVideoInteraction,
  type VideoInteractionCue,
  type VideoInteractionDocument,
  type ValidationIssue,
} from "@mind-imprint/course-contract";
import type { BlockSessionState } from "@mind-imprint/course-contract";
import type { AssetResolver, InteractionResult, SliceEmitter, VideoInteractionCompletedPayload } from "@mind-imprint/course-runtime";
import type { FillBlankBlock, SingleChoiceBlock, VideoBlock } from "../types";
import type { VideoEngine } from "../../media/videoEngine";
import { SingleChoiceRenderer } from "../assessment/SingleChoiceRenderer";
import { FillBlankRenderer } from "../assessment/FillBlankRenderer";
import { InteractionModal } from "./InteractionModal";

/**
 * The host resolves a Video Block's `interaction.source` to its parsed
 * {@link VideoInteractionDocument}, over the network — so this is an ASYNC
 * resource boundary (P1-01), not a synchronous lookup. Injected so previews,
 * drafts, and tests can supply a document (or a rejection) without a real
 * fetch. Must never throw synchronously; a failure to load rejects the
 * returned Promise.
 */
export type InteractionLoader = (source: string) => Promise<VideoInteractionDocument>;

/**
 * The renderer's typed failure vocabulary for an interaction load (P1-01
 * acceptance: "missing, malformed, mismatched, or expired" must all surface
 * as a visible, recoverable error — never a silent `null` or a deadlock).
 * A host {@link InteractionLoader} (Task 2) should reject with an
 * {@link InteractionLoadError} carrying one of these kinds — `not-found`
 * also covers an expired signed URL (403). Any other rejection reason is
 * treated as `not-found` (a generic "couldn't get it" bucket). `invalid` /
 * `mismatch` are additionally computed HERE, after a successful resolve, by
 * re-running {@link validateVideoInteraction} against the owning block — this
 * still catches a bad document even from a host that doesn't validate.
 */
export type InteractionLoadErrorKind = "not-found" | "malformed" | "invalid" | "mismatch";

export class InteractionLoadError extends Error {
  readonly kind: InteractionLoadErrorKind;
  constructor(kind: InteractionLoadErrorKind, message?: string) {
    super(message ?? `interaction document failed to load: ${kind}`);
    this.name = "InteractionLoadError";
    this.kind = kind;
  }
}

const InteractionLoaderContext = createContext<InteractionLoader | null>(null);
export const InteractionLoaderProvider = InteractionLoaderContext.Provider;
export function useInteractionLoader(): InteractionLoader | null {
  return useContext(InteractionLoaderContext);
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; document: VideoInteractionDocument }
  | { status: "error"; kind: InteractionLoadErrorKind; message: string };

const ERROR_MESSAGES: Record<InteractionLoadErrorKind, string> = {
  "not-found": "未能加载视频互动内容，请检查网络后重试。",
  malformed: "视频互动内容格式有误，无法解析。",
  invalid: "视频互动内容未通过校验，无法播放。",
  mismatch: "视频互动内容与该视频不匹配。",
};

/** Classifies referential issues from {@link validateVideoInteraction} into a load-error kind. */
function classifyValidationIssues(issues: ValidationIssue[]): InteractionLoadErrorKind {
  const isMismatch = issues.some((i) => i.path === "video.blockId" || i.path === "video.source");
  return isMismatch ? "mismatch" : "invalid";
}

export interface VideoInteractionControllerProps {
  block: VideoBlock;
  engine: VideoEngine;
  assetResolver: AssetResolver;
  emit: SliceEmitter;
  /** Called once every required cue has completed (gates the gated completion rule). */
  onRequiredCuesComplete: () => void;
  /**
   * The current layout visibility of the owning video block. The cue dialog
   * is portaled to `document.body` (escapes the block's own `hidden`
   * wrapper), so the controller must gate rendering on this itself — loading
   * continues in the background regardless.
   */
  visible: boolean;
  /** Bumped by {@link VideoRenderer}'s `reset` so cue fired/completed state and the required gate re-arm. */
  resetSignal?: number;
  /** Overrides the injected {@link InteractionLoader} for this instance (tests). */
  loader?: InteractionLoader;
}

const CUE_STATE: BlockSessionState = { visible: true, enabled: true, completed: false, attempts: 0 };

/**
 * §14 / §17.10 — a declarative media timeline (NOT a second workflow engine). It
 * watches the engine's reported `currentTime`, pauses at each cue, renders the
 * cue activity as an accessible modal by reusing the Slice 4 assessment
 * renderers, and resumes on completion or skip. Cue firing is idempotent (each
 * cue shows once) and tolerates seeks (a completed cue never re-fires). It
 * reports up when all required cues are done so {@link VideoRenderer} can gate
 * `block.completed`.
 */
export function VideoInteractionController({
  block,
  engine,
  assetResolver,
  emit,
  onRequiredCuesComplete,
  visible,
  resetSignal,
  loader,
}: VideoInteractionControllerProps) {
  const injectedLoader = useInteractionLoader();
  const load = loader ?? injectedLoader;

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [reloadNonce, setReloadNonce] = useState(0);

  // Async load: fetch (or reject) → validate against the owning block →
  // ready/error. Never leaves the caller with a silent `null`.
  useEffect(() => {
    let cancelled = false;
    const source = block.interaction?.source;
    if (!source) return; // VideoRenderer only mounts this controller when block.interaction is set.
    if (!load) {
      setLoadState({ status: "error", kind: "not-found", message: "未配置视频互动内容加载器。" });
      return;
    }
    setLoadState({ status: "loading" });
    load(source)
      .then((doc) => {
        if (cancelled) return;
        const issues = validateVideoInteraction(doc, block);
        if (issues.length > 0) {
          setLoadState({ status: "error", kind: classifyValidationIssues(issues), message: issues.map((i) => i.message).join("; ") });
          return;
        }
        setLoadState({ status: "ready", document: doc });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const kind = err instanceof InteractionLoadError ? err.kind : "not-found";
        const message = err instanceof Error ? err.message : String(err);
        setLoadState({ status: "error", kind, message });
      });
    return () => {
      cancelled = true;
    };
    // block.interaction.source is stable for a mounted controller; reloadNonce
    // deliberately re-triggers the same load on retry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block, load, reloadNonce]);

  const document = loadState.status === "ready" ? loadState.document : null;
  const cues = document?.video.cues ?? [];
  const requiredIds = useMemo(() => cues.filter((c) => c.required).map((c) => c.id), [cues]);

  const firedRef = useRef<Set<string>>(new Set());
  const completedRef = useRef<Set<string>>(new Set());
  const requiredDoneRef = useRef(false);
  const cueResultRef = useRef<InteractionResult>({});
  const [activeCue, setActiveCue] = useState<VideoInteractionCue | null>(null);
  // Mirror activeCue into a ref so the time listener always sees the latest value.
  const activeCueRef = useRef<VideoInteractionCue | null>(null);
  activeCueRef.current = activeCue;

  const checkRequiredDone = () => {
    if (requiredDoneRef.current) return;
    if (requiredIds.every((id) => completedRef.current.has(id))) {
      requiredDoneRef.current = true;
      onRequiredCuesComplete();
    }
  };

  // No required cues at all ⇒ the gate is satisfied immediately.
  useEffect(() => {
    if (document) checkRequiredDone();
    // Run once after the document resolves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document]);

  // Watch reported time; fire the first not-yet-shown cue whose time has passed.
  useEffect(() => {
    if (!document) return;
    return engine.onTimeUpdate((t) => {
      if (activeCueRef.current) return; // one cue at a time
      for (const cue of cues) {
        if (firedRef.current.has(cue.id)) continue;
        if (t >= cue.atSeconds) {
          firedRef.current.add(cue.id);
          cueResultRef.current = {};
          if (cue.pauseVideo) engine.pause();
          emit(block.id, "video.interaction.shown", { interactionId: cue.id });
          setActiveCue(cue);
          break;
        }
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document, engine]);

  // P2-03 — a `reset` (from VideoRenderer) clears fired/completed cue state and
  // the active cue; the required gate itself is re-armed by VideoRenderer
  // (its own `requiredCuesCompleteRef`). Skips the very first mount.
  const isFirstResetRun = useRef(true);
  useEffect(() => {
    if (isFirstResetRun.current) {
      isFirstResetRun.current = false;
      return;
    }
    firedRef.current.clear();
    completedRef.current.clear();
    requiredDoneRef.current = false;
    cueResultRef.current = {};
    setActiveCue(null);
    // Re-arms the "no required cues" immediate-gate case; a no-op when there
    // ARE required cues, since requiredDoneRef was just cleared above.
    checkRequiredDone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  const completeCue = (cue: VideoInteractionCue) => {
    if (completedRef.current.has(cue.id)) return;
    completedRef.current.add(cue.id);
    const payload: VideoInteractionCompletedPayload = { interactionId: cue.id, result: cueResultRef.current };
    emit(block.id, "video.interaction.completed", payload);
    setActiveCue(null);
    if (cue.pauseVideo) engine.play(); // resume
    checkRequiredDone();
  };

  const skipCue = (cue: VideoInteractionCue) => {
    // Optional-cue dismissal (P1-02, D1): resumes WITHOUT completing — never
    // added to completedRef, never gates required-cue completion. Still
    // recorded as process data (铁律④): skipping is a signal too.
    emit(block.id, "video.interaction.skipped", { interactionId: cue.id });
    setActiveCue(null);
    if (cue.pauseVideo) engine.play();
  };

  const retry = () => setReloadNonce((n) => n + 1);

  if (!visible) return null;

  if (loadState.status === "loading") {
    return (
      <p className="course-video__cue-status course-video__cue-status--loading" role="status" aria-live="polite">
        正在加载视频互动内容…
      </p>
    );
  }

  if (loadState.status === "error") {
    return (
      <div className="course-video__cue-status course-video__cue-status--error" role="alert">
        <p>{ERROR_MESSAGES[loadState.kind]}</p>
        <button type="button" className="course-video__cue-retry" onClick={retry}>
          重试
        </button>
      </div>
    );
  }

  if (!activeCue) return null;

  // A local emitter isolates the cue's answer events from the Slice Workflow
  // (§14): it accumulates the inner activity's evidence into a typed
  // {@link InteractionResult} (P1-02) and turns only the inner
  // `block.completed` into a cue completion.
  const cueEmit: SliceEmitter = (_sourceId, type, payload) => {
    const record = payload && typeof payload === "object" && !Array.isArray(payload) ? (payload as Record<string, unknown>) : undefined;
    switch (type) {
      case "answer.submitted":
        if (record && "value" in record) cueResultRef.current = { ...cueResultRef.current, value: record.value };
        return;
      case "answer.correct":
        cueResultRef.current = { ...cueResultRef.current, correct: true };
        return;
      case "answer.incorrect":
      case "answer.attemptsExhausted":
        cueResultRef.current = { ...cueResultRef.current, correct: false };
        return;
      case "block.completed":
        completeCue(activeCue);
        return;
      default:
        return;
    }
  };

  return (
    <InteractionModal ariaLabel={activeCue.prompt} onSkip={activeCue.required ? undefined : () => skipCue(activeCue)}>
      {/* The cue prompt is rendered by the inner assessment renderer
          (renderCueActivity passes cue.prompt as the block prompt); a second
          <p> here would duplicate it inside the dialog. */}
      {renderCueActivity(activeCue, assetResolver, cueEmit)}
    </InteractionModal>
  );
}

/** Renders the cue's activity by reusing the Slice 4 assessment renderers. */
function renderCueActivity(cue: VideoInteractionCue, assetResolver: AssetResolver, emit: SliceEmitter) {
  if (cue.activity.type === "singleChoice") {
    const block: SingleChoiceBlock = {
      id: cue.id,
      type: "singleChoice",
      prompt: cue.prompt,
      options: cue.activity.options,
      assessment: cue.activity.assessment,
      completion: cue.activity.completion,
    };
    return (
      <SingleChoiceRenderer block={block} assetResolver={assetResolver} state={CUE_STATE} visible enabled emit={emit} />
    );
  }
  const block: FillBlankBlock = {
    id: cue.id,
    type: "fillBlank",
    prompt: cue.prompt,
    assessment: cue.activity.assessment,
    completion: cue.activity.completion,
  };
  return <FillBlankRenderer block={block} assetResolver={assetResolver} state={CUE_STATE} visible enabled emit={emit} />;
}
