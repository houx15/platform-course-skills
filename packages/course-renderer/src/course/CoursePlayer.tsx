import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  validateCourseDefinition,
  CourseSession,
  isCourseSessionStale,
  type CourseDefinition,
  type RuntimeSceneResult,
  type SliceDefinition,
  type SliceSessionState,
  type ValidationIssue,
} from "@mind-imprint/course-contract";
import {
  RuntimeEventBus,
  type Clock,
  type ClosingSceneInput,
  type CourseRuntimeAdapters,
  type IdFactory,
  type OpeningSceneInput,
} from "@mind-imprint/course-runtime";
import { SlicePlayer } from "../slice/SlicePlayer";
import { OpeningScene } from "../scenes/OpeningScene";
import { ClosingScene } from "../scenes/ClosingScene";
import { buildClosingSessionEvidence } from "./sessionEvidence";
// §Slice5 / P1-06 — the renderer-owned stylesheet. Side-effect import: since
// CoursePlayer is the package's actual runtime mount root, every consumer
// (direct import or via the package's `index.ts` re-export) pulls this in.
import "../styles/course.css";

export interface CoursePlayerProps {
  document: unknown;
  /**
   * D5 / P2-08 — the CURRENT definition's content hash (the host's GET
   * /courses/{slug}/definition response's `hash`), used to detect a resumed
   * session built against a definition that has since been edited. Omitted
   * (e.g. a host with no revision-hash endpoint, or most tests) simply
   * disables the check — every session resumes exactly as it did before this
   * field existed, matching `isCourseSessionStale`'s back-compat contract.
   */
  definitionHash?: string;
  adapters: CourseRuntimeAdapters;
  studentId: string;
  /** Restore an existing session instead of creating one. */
  sessionId?: string;
  /** Deterministic factories for the event bus (§16 replayability). */
  idFactory: IdFactory;
  clock: Clock;
  /** Fires once the event bus is built. Test/host seam for observing the bus. */
  onBusReady?: (bus: RuntimeEventBus) => void;
  /**
   * Fires once the learner dismisses the Closing scene (§6.2 / P1-03) — the
   * ONLY authoritative completion signal for the host. The session already
   * transitions `in-progress -> closing -> completed` on its own; do NOT
   * infer UI completion by wrapping `setStatus("completed")` — the Closing
   * scene is rendered and playable for as long as the learner stays on it,
   * and only THIS callback means "the host may now navigate away."
   */
  onComplete?: () => void;
  /**
   * P2-05 — host-supplied resolver for the Opening's allowed history signals
   * (the course's own `OpeningSignal` enum: "recent-course-topics" |
   * "prior-objective-performance"). Called once, at init, ONLY when the
   * Opening permits at least one signal — with exactly that allowed list, so
   * the resolver never has to re-derive permission. The renderer never
   * invents values itself: omit the prop (or a key in its return value) when
   * the host has nothing honest to offer for a signal; `signalValues` then
   * simply omits that key, same as if personalization were disabled.
   */
  signalResolver?: (allowedSignals: string[]) => Record<string, unknown> | Promise<Record<string, unknown>>;
  /**
   * Fires whenever the phase or current Slice changes, so a host chrome (e.g. a
   * progress bar) can reflect where the learner is without owning the runtime's
   * navigation. `sliceIndex` is 0-based into the flattened Slice list;
   * `sliceCount` is its length. The renderer stays chrome-agnostic — it only
   * reports; the host decides how (or whether) to show progress.
   */
  onProgress?: (progress: CourseProgress) => void;
}

type Phase = "loading" | "error" | "opening" | "playing" | "closing";

/** Host progress signal emitted by {@link CoursePlayer} via `onProgress`. */
export interface CourseProgress {
  phase: Phase;
  sliceIndex: number;
  sliceCount: number;
}

interface SliceEntry {
  partId: string;
  slice: SliceDefinition;
}

function flattenSlices(course: CourseDefinition): SliceEntry[] {
  const entries: SliceEntry[] = [];
  for (const part of course.parts) {
    for (const slice of part.slices) entries.push({ partId: part.id, slice });
  }
  return entries;
}

function ErrorSurface({ issues }: { issues: ValidationIssue[] }) {
  return (
    <section className="course-error" role="alert" aria-label="课程无法播放" data-course-error="true">
      <h2>课程定义无法播放</h2>
      <ul className="course-error__issues">
        {issues.map((issue, i) => (
          <li key={i} data-issue-layer={issue.layer}>
            <code>{issue.path || "(root)"}</code>: {issue.message}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * §17.3 / §6 / §13 — the course-level lifecycle: validate → Opening → the linear
 * Part/Slice walk → Closing. Opening and Closing text come through the injected
 * scene generators (fallback path is exercised in this slice). Structurally
 * invalid documents render a diagnostic surface and never mount a SlicePlayer.
 */
export function CoursePlayer({ document, definitionHash, adapters, studentId, sessionId, idFactory, clock, onBusReady, onComplete, onProgress, signalResolver }: CoursePlayerProps) {
  const validation = useMemo(() => validateCourseDefinition(document), [document]);

  const [phase, setPhase] = useState<Phase>(validation.ok ? "loading" : "error");
  const [opening, setOpening] = useState<RuntimeSceneResult | null>(null);
  const [closing, setClosing] = useState<RuntimeSceneResult | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  // D5 / P2-08 — set once, at init, when a resumed session's own recorded
  // hash disagreed with `definitionHash` and its progress was discarded.
  const [revisionNotice, setRevisionNotice] = useState(false);
  const indexRef = useRef(0);
  const [bus, setBus] = useState<RuntimeEventBus | null>(null);
  const activeSessionId = useRef<string | null>(null);

  const course = validation.ok ? validation.course : null;
  const entries = useMemo(() => (course ? flattenSlices(course) : []), [course]);

  // Report progress to the host (chrome-agnostic): fire on every phase / slice
  // change. Ref'd so a host passing a fresh callback each render never loops.
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;
  useEffect(() => {
    onProgressRef.current?.({ phase, sliceIndex: currentIndex, sliceCount: entries.length });
  }, [phase, currentIndex, entries.length]);

  // §Slice4 / P1-05 — the live cache of every Slice's own persisted state,
  // keyed by Slice id: seeded once from the (possibly-restored) session's
  // `sliceStates` at init, then kept current by each mounted SlicePlayer's
  // `onStateChange`. Drives BOTH kinds of "already reached" mounts — the
  // original mid-course reload resume AND any later Previous/Next revisit —
  // through the SAME lookup, so a Slice is shown restored (completed Slices
  // never re-fire their terminal effects) no matter which path got there.
  const sliceStatesRef = useRef<Record<string, SliceSessionState>>({});

  // Init once: restore (validated) or create the session, build the bus,
  // resolve Opening/Closing without a redundant generator call when the
  // session already carries them, and land on the right phase/position.
  const initRan = useRef(false);
  useEffect(() => {
    if (!course || initRan.current) return;
    initRan.current = true;
    let cancelled = false;

    const placeholderScene = (): RuntimeSceneResult => ({
      text: "",
      generatedAt: clock(),
      usedSignalTypes: [],
      fallbackUsed: true,
    });

    void (async () => {
      // The authoritative session: `load(sessionId)` when the host passed one,
      // else the get-or-create `create()` call — which is ALSO authoritative
      // (the server returns the persisted, possibly in-progress/closing/
      // completed session for this student+course, not merely a blank one).
      // Resume must key off THIS session's own state, never off whether a
      // `sessionId` prop happened to be passed in.
      const fetched = sessionId
        ? await adapters.sessionAdapter.load(sessionId)
        : await adapters.sessionAdapter.create({ courseId: course.id, studentId });
      if (cancelled) return;

      // Validate at the boundary (§16): a malformed/incompatible session must
      // degrade to a fresh start, never crash the player.
      const parsedFetched = fetched ? CourseSession.safeParse(fetched) : null;
      let restored = parsedFetched?.success ? parsedFetched.data : null;

      let session: CourseSession;
      if (restored) {
        session = restored;
      } else {
        // `load()` missed (or returned something unparsable) — get-or-create a
        // known-good session directly. (If `fetched` already came from
        // `create()` and still failed to parse, this repeats the call; the
        // get-or-create operation is idempotent server-side.)
        const created = await adapters.sessionAdapter.create({ courseId: course.id, studentId });
        if (cancelled) return;
        const parsedCreated = CourseSession.safeParse(created);
        restored = parsedCreated.success ? parsedCreated.data : null;
        session = restored ?? created;
      }

      activeSessionId.current = session.id;

      // D5 / P2-08 — content-hash revision policy: a session whose OWN
      // recorded hash actively disagrees with the current definition's hash
      // may reference slice/step/block ids the definition no longer has —
      // never restore its progress. A session with no recorded hash yet
      // (pre-existing, or brand new) is never stale (isCourseSessionStale's
      // back-compat contract); stamp the current hash either way so this
      // session's NEXT resume compares against what it's actually built on.
      const stale = definitionHash != null && isCourseSessionStale(session, definitionHash);
      if (stale) {
        setRevisionNotice(true);
        // Durability: clear the session's PERSISTED `current`/`sliceStates`,
        // not just the renderer's in-memory cache below — otherwise once
        // setDefinitionHash (next) makes the hash match, the NEXT resume
        // would see the still-persisted stale state and silently restore
        // exactly what this reset meant to discard. Awaited (unlike the
        // fire-and-forget setDefinitionHash below) so the reset is committed
        // before this session is treated as fresh for the rest of init.
        await adapters.sessionAdapter.resetProgress(session.id);
        if (cancelled) return;
      }
      if (definitionHash && session.courseDefinitionHash !== definitionHash) {
        void adapters.sessionAdapter.setDefinitionHash(session.id, definitionHash);
      }

      // §Slice4 — seed the revisit/previous cache from whatever this session
      // already has recorded, so a Slice reached before THIS mount (a prior
      // page load) is just as "already reached" as one visited this session.
      // A stale session's cache is discarded outright (D5) — it may key
      // blocks the current definition no longer has.
      sliceStatesRef.current = stale ? {} : { ...session.sliceStates };
      const newBus = new RuntimeEventBus({ courseId: course.id, sessionId: session.id, idFactory, clock });
      setBus(newBus);
      onBusReady?.(newBus);

      // A session that carries real progress resumes from ITS OWN state —
      // never let the "fresh session" path below overwrite the server's
      // status back to "opening" once the student is already further along.
      // A stale session is treated as having NO progress regardless of its
      // recorded status/current (D5 — never restore stale state).
      const progressStatuses = new Set<CourseSession["status"]>(["in-progress", "closing", "completed"]);
      const hasProgress = !stale && restored != null && (progressStatuses.has(restored.status) || restored.current != null);

      if (hasProgress) {
        // Completed, OR closing-but-not-yet-dismissed (the learner reloaded
        // before clicking "完成课程"), with a saved Closing — restore
        // straight to Closing, never regenerate or reset to Opening/index 0,
        // and never touch status (a "closing" session stays "closing" until
        // the learner's own dismissal completes it — see handleCompleteClosing).
        if ((restored!.status === "completed" || restored!.status === "closing") && restored!.closing) {
          setOpening(restored!.opening ?? placeholderScene());
          setClosing(restored!.closing);
          setPhase("closing");
          return;
        }

        // Resume mid-course: land back on the exact Slice + workflow step
        // (+ block state) the student left off at, skipping Opening entirely.
        const resumeIndex = restored!.current
          ? entries.findIndex((e) => e.partId === restored!.current!.partId && e.slice.id === restored!.current!.sliceId)
          : -1;
        if (resumeIndex >= 0) {
          // The loading guard below requires a non-null `opening`, even though
          // the Opening scene itself is never shown on this path.
          setOpening(restored!.opening ?? placeholderScene());
          indexRef.current = resumeIndex;
          setCurrentIndex(resumeIndex);
          setPhase("playing");
          return;
        }

        // Progress exists but the exact Slice couldn't be located (e.g. course
        // content changed since the session started, or Closing hasn't been
        // saved yet) — still never regress the session's own status back to
        // "opening"; restart the walk at index 0 without touching status.
        setOpening(restored!.opening ?? placeholderScene());
        indexRef.current = 0;
        setCurrentIndex(0);
        setPhase("playing");
        return;
      }

      await adapters.sessionAdapter.setStatus(session.id, "opening");

      // A session that already has a saved Opening (e.g. reloaded before
      // clicking start) restores it instead of paying for regeneration. A
      // stale session's saved Opening is discarded too (D5) — it was
      // generated against the old definition's objectives/preview copy.
      if (!stale && restored?.opening) {
        setOpening(restored.opening);
        setPhase("opening");
        return;
      }

      // P2-05 — resolve real signal values only when the Opening actually
      // permits at least one, and only via the host's own resolver; with no
      // resolver wired (or nothing permitted), signalValues stays empty
      // rather than fabricated.
      const openingAllowedSignals = course.opening.personalization.enabled ? course.opening.personalization.allowedSignals : [];
      const signalValues = openingAllowedSignals.length > 0 && signalResolver ? await signalResolver(openingAllowedSignals) : {};

      const input: OpeningSceneInput = {
        which: "opening",
        title: course.title,
        estimatedMinutes: course.estimatedMinutes,
        objectives: course.objectives.map((o) => o.text),
        learningPreview: course.opening.learningPreview,
        allowedSignals: openingAllowedSignals,
        signalValues,
        fallback: {
          text: course.opening.fallback.text,
          audioUrl: course.opening.fallback.audio ? adapters.assetResolver.resolve(course.opening.fallback.audio) : undefined,
        },
      };
      const result = await adapters.openingGenerator.generate(input);
      if (cancelled) return;
      await adapters.sessionAdapter.saveScene(session.id, "opening", result);
      setOpening(result);
      setPhase("opening");
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // §16 resume — record which Slice is active whenever it changes, so a later
  // reload's `current` lookup (above) has somewhere to land.
  useEffect(() => {
    if (phase !== "playing") return;
    const sid = activeSessionId.current;
    const entry = entries[currentIndex];
    if (!sid || !entry) return;
    void adapters.sessionAdapter.setCurrent(sid, {
      partId: entry.partId,
      sliceId: entry.slice.id,
      workflowStepId: entry.slice.workflow.initialStepId,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, currentIndex]);

  const handleStart = () => {
    const sid = activeSessionId.current;
    if (sid) void adapters.sessionAdapter.setStatus(sid, "in-progress");
    indexRef.current = 0;
    setCurrentIndex(0);
    setPhase("playing");
  };

  // §P1-03 — Closing is an explicit lifecycle phase, not a side-effect of
  // completion: the session moves to "closing" and the scene renders/plays
  // BEFORE any "completed" write, so the learner is guaranteed to see (and
  // hear) it — the production host's onFinish-on-completion wrapper can no
  // longer unmount the player out from under it. "completed" is only set
  // once the learner dismisses via handleCompleteClosing.
  const runClosing = async () => {
    if (!course) return;
    const sid = activeSessionId.current;
    if (sid) await adapters.sessionAdapter.setStatus(sid, "closing");

    // P2-05 — derive real evidence from the session's OWN recorded state
    // (never host-supplied, never fabricated): re-load the just-updated
    // session (the last slice's completion already persisted synchronously
    // via saveSliceState) and pull only the facts the course's own
    // allowedSignals permit.
    const closingAllowedSignals = course.closing.personalization.enabled ? course.closing.personalization.allowedSignals : [];
    let sessionEvidence: Record<string, unknown> = {};
    if (sid && closingAllowedSignals.length > 0) {
      const latest = await adapters.sessionAdapter.load(sid);
      const parsed = latest ? CourseSession.safeParse(latest) : null;
      if (parsed?.success) sessionEvidence = buildClosingSessionEvidence(parsed.data, closingAllowedSignals);
    }

    const input: ClosingSceneInput = {
      which: "closing",
      preparedSummary: course.closing.preparedSummary,
      takeaways: course.closing.takeaways,
      transferApplications: course.closing.transferApplications,
      allowedSignals: closingAllowedSignals,
      sessionEvidence,
      fallback: {
        text: course.closing.fallback.text,
        audioUrl: course.closing.fallback.audio ? adapters.assetResolver.resolve(course.closing.fallback.audio) : undefined,
      },
    };
    const result = await adapters.closingGenerator.generate(input);
    if (sid) await adapters.sessionAdapter.saveScene(sid, "closing", result);
    setClosing(result);
    setPhase("closing");
  };

  // The Closing completion policy (§P1-03): the learner's explicit "完成课程"
  // dismissal — nothing else marks the session completed or tells the host
  // it may navigate away.
  const handleCompleteClosing = async () => {
    const sid = activeSessionId.current;
    if (sid) await adapters.sessionAdapter.setStatus(sid, "completed");
    onComplete?.();
  };

  const handleNavigateNext = () => {
    const next = indexRef.current + 1;
    if (next >= entries.length) {
      void runClosing();
      return;
    }
    indexRef.current = next;
    setCurrentIndex(next);
  };

  // §Slice4 / P1-05 — "上一步": always the immediately-preceding Slice, which
  // by construction of the linear walk is always already reached. Passed to
  // SlicePlayer's `onNavigatePrevious` only when `currentIndex > 0` below —
  // omitted entirely (not merely disabled) before the first Slice.
  const handleNavigatePrevious = () => {
    const prev = indexRef.current - 1;
    if (prev < 0) return;
    indexRef.current = prev;
    setCurrentIndex(prev);
  };

  // §Slice5 / P1-06 (D6) — every phase renders inside ONE shell that fills
  // its viewport region and never page-scrolls (`.course-shell`, defined in
  // `styles/course.css`). Computed as a local `content` var rather than
  // returning early per-phase so exactly one shell wraps whichever phase is
  // active — the phase branching itself is unchanged.
  let content: ReactNode;

  if (phase === "error" || !course) {
    content = <ErrorSurface issues={validation.ok ? [] : validation.issues} />;
  } else if (phase === "loading" || !opening || !bus) {
    content = <div className="course-loading" aria-busy="true" />;
  } else if (phase === "opening") {
    content = (
      <OpeningScene
        scene={opening}
        title={course.title}
        estimatedMinutes={course.estimatedMinutes}
        objectives={course.objectives.map((o) => o.text)}
        learningPreview={course.opening.learningPreview}
        assetResolver={adapters.assetResolver}
        onStart={handleStart}
      />
    );
  } else if (phase === "closing" && closing) {
    content = (
      <ClosingScene
        scene={closing}
        summary={course.closing.preparedSummary}
        takeaways={course.closing.takeaways}
        transferApplications={course.closing.transferApplications}
        assetResolver={adapters.assetResolver}
        onComplete={handleCompleteClosing}
      />
    );
  } else {
    const entry = entries[currentIndex]!;
    // §Slice4 / P1-05 — a Slice this index has already reached (this session's
    // resume, or an earlier visit via Previous/Next) restores from the cache;
    // a never-before-reached Slice gets no restoreState and starts fresh.
    const cachedState = sliceStatesRef.current[entry.slice.id];
    content = (
      <div className="course-player" data-phase="playing">
        <SlicePlayer
          key={entry.slice.id}
          slice={entry.slice}
          partId={entry.partId}
          sessionId={activeSessionId.current!}
          adapters={adapters}
          bus={bus}
          onSliceComplete={() => {}}
          onNavigateNext={handleNavigateNext}
          onNavigatePrevious={currentIndex > 0 ? handleNavigatePrevious : undefined}
          onStateChange={(next) => {
            sliceStatesRef.current = { ...sliceStatesRef.current, [entry.slice.id]: next };
          }}
          restoreStepId={cachedState?.currentWorkflowStepId}
          restoreState={cachedState}
        />
      </div>
    );
  }

  return (
    <div className="course-shell" data-course-shell="true">
      {/* D5 / P2-08 — brief, visible, dismissible notice: the resumed session's
          progress was reset because the course definition changed since it
          was built (see the `stale` branch in the init effect above). */}
      {revisionNotice && (
        <div className="course-revision-notice" role="status" data-testid="course-revision-notice">
          <span>课程已更新，进度已重置</span>
          <button type="button" onClick={() => setRevisionNotice(false)}>
            知道了
          </button>
        </div>
      )}
      {content}
    </div>
  );
}
