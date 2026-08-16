import { z } from "zod";
import { blockIdSchema, narrationIdSchema, workflowStepIdSchema } from "./primitives";

export const TargetRef = z.union([
  z.object({ blockId: blockIdSchema }).strict(),
  z.object({ blockId: blockIdSchema, itemId: z.string().min(1) }).strict(),
]);

export const WorkflowAction = z.discriminatedUnion("type", [
  z.object({ type: z.literal("show"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("hide"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("focus"), target: TargetRef }).strict(),
  z.object({ type: z.literal("clearFocus") }).strict(),
  z.object({ type: z.literal("enable"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("disable"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("playNarration"), narrationId: narrationIdSchema }).strict(),
  z.object({ type: z.literal("pauseNarration"), narrationId: narrationIdSchema }).strict(),
  z.object({ type: z.literal("stopNarration"), narrationId: narrationIdSchema }).strict(),
  z.object({ type: z.literal("playBlock"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("pauseBlock"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("resetBlock"), targetId: blockIdSchema }).strict(),
  z.object({ type: z.literal("startTimer"), timerId: z.string().min(1), durationSeconds: z.number().positive() }).strict(),
  z.object({ type: z.literal("cancelTimer"), timerId: z.string().min(1) }).strict(),
  z.object({ type: z.literal("completeSlice") }).strict(),
  z.object({ type: z.literal("navigate"), target: z.literal("nextSlice") }).strict(),
]);

export const WorkflowEventType = z.enum([
  "narration.ended",
  "video.started",
  "video.paused",
  "video.ended",
  "video.interaction.shown",
  "video.interaction.completed",
  "pdf.opened",
  "pdf.pageChanged",
  "interaction.completed",
  "answer.submitted",
  "answer.correct",
  "answer.incorrect",
  "answer.attemptsExhausted",
  "block.completed",
  "student.continue",
  "timer.elapsed",
]);

export const WorkflowEventMatcher = z
  .object({
    type: WorkflowEventType,
    sourceId: z.string().min(1).optional(),
    interactionId: z.string().min(1).optional(),
    timerId: z.string().min(1).optional(),
  })
  .strict();

export const WorkflowTransition = z.object({ on: WorkflowEventMatcher, to: workflowStepIdSchema }).strict();

export const WorkflowStep = z
  .object({ id: workflowStepIdSchema, enterActions: z.array(WorkflowAction), transitions: z.array(WorkflowTransition) })
  .strict();

export const SliceInitialState = z
  .object({
    visibleBlockIds: z.array(blockIdSchema).optional(),
    enabledBlockIds: z.array(blockIdSchema).optional(),
    focusedTarget: TargetRef.optional(),
  })
  .strict();

export const SliceWorkflow = z
  .object({
    version: z.literal("1.0"),
    initialStepId: workflowStepIdSchema,
    initialState: SliceInitialState.optional(),
    steps: z.array(WorkflowStep).min(1),
  })
  .strict();

export type WorkflowAction = z.infer<typeof WorkflowAction>;
export type WorkflowEventType = z.infer<typeof WorkflowEventType>;
export type WorkflowEventMatcher = z.infer<typeof WorkflowEventMatcher>;
export type WorkflowTransition = z.infer<typeof WorkflowTransition>;
export type WorkflowStep = z.infer<typeof WorkflowStep>;
export type SliceInitialState = z.infer<typeof SliceInitialState>;
export type SliceWorkflow = z.infer<typeof SliceWorkflow>;
export type TargetRef = z.infer<typeof TargetRef>;
