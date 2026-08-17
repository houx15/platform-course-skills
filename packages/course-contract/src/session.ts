import { z } from "zod";
import { courseIdSchema, partIdSchema, sliceIdSchema, blockIdSchema, workflowStepIdSchema } from "./primitives";
import { WorkflowEventType } from "./workflow";

export const RuntimeSceneResult = z
  .object({
    text: z.string(),
    audioUrl: z.string().optional(),
    generatedAt: z.string(),
    usedSignalTypes: z.array(z.string()),
    fallbackUsed: z.boolean(),
  })
  .strict();

export const BlockSessionState = z
  .object({
    visible: z.boolean(),
    enabled: z.boolean(),
    completed: z.boolean(),
    attempts: z.number().int().nonnegative().optional(),
    answer: z.unknown().optional(),
    mediaPositionSeconds: z.number().nonnegative().optional(),
    interactionResult: z.unknown().optional(),
  })
  .strict();

export const SliceSessionState = z
  .object({
    status: z.enum(["not-started", "in-progress", "completed"]),
    currentWorkflowStepId: workflowStepIdSchema.optional(),
    startedAt: z.string().optional(),
    completedAt: z.string().optional(),
    elapsedSeconds: z.number().nonnegative(),
    blockStates: z.record(blockIdSchema, BlockSessionState),
  })
  .strict();

export const CourseRuntimeEvent = z
  .object({
    id: z.string(),
    sessionId: z.string(),
    courseId: courseIdSchema,
    partId: partIdSchema.optional(),
    sliceId: sliceIdSchema.optional(),
    sourceId: z.string(),
    type: z.union([WorkflowEventType, z.string()]),
    occurredAt: z.string(),
    payload: z.unknown(),
  })
  .strict();

export const CourseSession = z
  .object({
    id: z.string(),
    courseId: courseIdSchema,
    courseSchemaVersion: z.literal("2.0"),
    studentId: z.string(),
    status: z.enum(["created", "opening", "in-progress", "closing", "completed"]),
    startedAt: z.string().optional(),
    completedAt: z.string().optional(),
    current: z.object({ partId: partIdSchema, sliceId: sliceIdSchema, workflowStepId: workflowStepIdSchema }).strict().optional(),
    opening: RuntimeSceneResult.optional(),
    sliceStates: z.record(sliceIdSchema, SliceSessionState),
    events: z.array(CourseRuntimeEvent),
    closing: RuntimeSceneResult.optional(),
    /**
     * D5 / P2-08 — the CourseDefinition content-hash (sha256 hex, computed
     * server-side over the stored `course_definition` bytes — see
     * apps/api/internal/api/course_definition.go) this session's own state was
     * last built/resumed against. Optional so a session persisted BEFORE this
     * field existed still parses (back-compat) — see `isCourseSessionStale`.
     */
    courseDefinitionHash: z.string().optional(),
  })
  .strict();

export type CourseSession = z.infer<typeof CourseSession>;
export type SliceSessionState = z.infer<typeof SliceSessionState>;
export type BlockSessionState = z.infer<typeof BlockSessionState>;
export type CourseRuntimeEvent = z.infer<typeof CourseRuntimeEvent>;
export type RuntimeSceneResult = z.infer<typeof RuntimeSceneResult>;

/**
 * D5 / P2-08 — pure comparison helper for the content-hash revision policy.
 * The real sha256 of a stored CourseDefinition is computed once, server-side
 * (Go hashes the stored bytes directly — see course_definition.go); this stays
 * a plain string comparison so it's usable from the pure contract package
 * without pulling Web Crypto/Node's `crypto` into it (determinism constraint).
 *
 * A session with NO recorded hash — created before this field existed, or a
 * brand-new session not yet stamped — is never "stale": the safe back-compat
 * reading is resume-as-normal, not a surprise reset. Only a PRESENT hash that
 * actively disagrees with the current definition's hash means the session's
 * slice/step/block state may reference ids the definition no longer has.
 */
export function isCourseSessionStale(
  session: Pick<CourseSession, "courseDefinitionHash">,
  currentDefinitionHash: string,
): boolean {
  return session.courseDefinitionHash != null && session.courseDefinitionHash !== currentDefinitionHash;
}
