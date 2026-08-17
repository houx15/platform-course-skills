import type { CourseRuntimeEvent, CourseSession, RuntimeSceneResult, SliceSessionState } from "@mind-imprint/course-contract";

/**
 * Host-supplied injection seams. The runtime never reads the wall clock or
 * generates ids itself (§16 replayability): the host passes deterministic
 * factories so tests and replays produce identical output.
 */
export type IdFactory = () => string;
/** Returns an ISO-8601 timestamp string. */
export type Clock = () => string;

/**
 * §4 — converts an authored relative asset path into a resolvable URL (local
 * preview, draft, or production CDN). The package never resolves paths itself.
 */
export interface AssetResolver {
  resolve(relativePath: string): string;
}

/** Input for {@link SessionAdapter.create}. Session id/timestamps are the adapter's concern. */
export interface CreateSessionInput {
  courseId: string;
  studentId: string;
}

/** Which prepared runtime scene a result belongs to (§6). */
export type SceneSlot = "opening" | "closing";

/**
 * §16 — the persistence surface the runtime needs. Kept minimal but sufficient
 * for Slice 3 (renderer) and Slice 8 (API-backed adapter). Backends are free to
 * batch or debounce; the interface only expresses intent.
 */
export interface SessionAdapter {
  load(sessionId: string): Promise<CourseSession | null>;
  create(input: CreateSessionInput): Promise<CourseSession>;
  appendEvent(sessionId: string, event: CourseRuntimeEvent): Promise<void>;
  saveSliceState(sessionId: string, sliceId: string, state: SliceSessionState): Promise<void>;
  saveScene(sessionId: string, which: SceneSlot, result: RuntimeSceneResult): Promise<void>;
  setStatus(sessionId: string, status: CourseSession["status"]): Promise<void>;
  /** §16 resume — records which part/slice/workflow-step is currently active, so a later restore knows where to jump back to. */
  setCurrent(sessionId: string, current: CourseSession["current"]): Promise<void>;
  /**
   * D5 / P2-08 — records which CourseDefinition content-hash this session's
   * current state was built/reset against, so a LATER resume can detect a
   * course edited out from under it (@mind-imprint/course-contract's
   * `isCourseSessionStale`). CoursePlayer calls this once per init: on a
   * brand-new session (no hash yet) and again after a stale-hash reset.
   */
  setDefinitionHash(sessionId: string, hash: string): Promise<void>;
  /**
   * D5 / P2-08 durability — clears a session's PERSISTED progress (`current`
   * and `sliceStates`) so a stale-hash reset survives a reload. Without this,
   * a reset only ever touched the renderer's in-memory cache
   * (`sliceStatesRef`); the next `load()` would see the still-persisted
   * `current`/`sliceStates` and, once `setDefinitionHash` had already made
   * the hash match, silently resurrect the discarded progress. CoursePlayer
   * calls this in the same stale-reset branch that stamps the new hash.
   */
  resetProgress(sessionId: string): Promise<void>;
}

/**
 * §6.1 — approved facts + permitted signals handed to the opening generator.
 * Carries no raw prompt: model identifiers and templates are platform config.
 */
export interface OpeningSceneInput {
  which: "opening";
  title: string;
  estimatedMinutes: number;
  objectives: string[];
  learningPreview: string[];
  allowedSignals: string[];
  /** Resolved values for the allowed student-history signals (empty when disabled). */
  signalValues: Record<string, unknown>;
  fallback: { text: string; audioUrl?: string };
}

/** §6.2 — approved facts + permitted signals + real session evidence for the closing generator. */
export interface ClosingSceneInput {
  which: "closing";
  preparedSummary: string;
  takeaways: string[];
  transferApplications: string[];
  allowedSignals: string[];
  /** Evidence drawn from the actual CourseSession (only facts that exist). */
  sessionEvidence: Record<string, unknown>;
  fallback: { text: string; audioUrl?: string };
}

export type SceneGenerationInput = OpeningSceneInput | ClosingSceneInput;

/**
 * §6.3, §17.16 — produces a RuntimeSceneResult (text + optional audio) or a
 * fallback-flagged result when generation/speech synthesis fails. Real backends
 * are Slice 7; this package ships only the interface.
 */
export interface RuntimeSceneGenerator {
  generate(input: SceneGenerationInput): Promise<RuntimeSceneResult>;
}

/** §17.16 — the full adapter set CourseRenderer depends on from its host. */
export interface CourseRuntimeAdapters {
  assetResolver: AssetResolver;
  sessionAdapter: SessionAdapter;
  openingGenerator: RuntimeSceneGenerator;
  closingGenerator: RuntimeSceneGenerator;
}

const clone = <T>(value: T): T => structuredClone(value);

/**
 * A concrete, deterministic {@link SessionAdapter} backed by an in-memory Map.
 * Used by later slices' tests and the local preview app. Stored sessions are
 * deep-cloned on the way in and out so callers can never alias internal state.
 */
export class InMemorySessionAdapter implements SessionAdapter {
  private readonly sessions = new Map<string, CourseSession>();
  private readonly idFactory: IdFactory;
  private readonly clock: Clock;

  constructor(opts: { idFactory: IdFactory; clock: Clock }) {
    this.idFactory = opts.idFactory;
    this.clock = opts.clock;
  }

  async load(sessionId: string): Promise<CourseSession | null> {
    const found = this.sessions.get(sessionId);
    return found ? clone(found) : null;
  }

  async create(input: CreateSessionInput): Promise<CourseSession> {
    const session: CourseSession = {
      id: this.idFactory(),
      courseId: input.courseId,
      courseSchemaVersion: "2.0",
      studentId: input.studentId,
      status: "created",
      sliceStates: {},
      events: [],
    };
    this.sessions.set(session.id, clone(session));
    return clone(session);
  }

  async appendEvent(sessionId: string, event: CourseRuntimeEvent): Promise<void> {
    const session = this.require(sessionId);
    session.events.push(clone(event));
  }

  async saveSliceState(sessionId: string, sliceId: string, state: SliceSessionState): Promise<void> {
    const session = this.require(sessionId);
    session.sliceStates[sliceId] = clone(state);
  }

  async saveScene(sessionId: string, which: SceneSlot, result: RuntimeSceneResult): Promise<void> {
    const session = this.require(sessionId);
    session[which] = clone(result);
  }

  async setStatus(sessionId: string, status: CourseSession["status"]): Promise<void> {
    this.require(sessionId).status = status;
  }

  async setCurrent(sessionId: string, current: CourseSession["current"]): Promise<void> {
    this.require(sessionId).current = current ? clone(current) : undefined;
  }

  async setDefinitionHash(sessionId: string, hash: string): Promise<void> {
    this.require(sessionId).courseDefinitionHash = hash;
  }

  async resetProgress(sessionId: string): Promise<void> {
    const session = this.require(sessionId);
    session.current = undefined;
    session.sliceStates = {};
  }

  private require(sessionId: string): CourseSession {
    const session = this.sessions.get(sessionId);
    if (!session) throw new Error(`InMemorySessionAdapter: unknown session '${sessionId}'`);
    return session;
  }
}
