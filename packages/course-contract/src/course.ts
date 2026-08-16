import { z } from "zod";
import { courseIdSchema, objectiveIdSchema, partIdSchema, sliceIdSchema, blockIdSchema, relativeAssetPathSchema } from "./primitives";
import { BlockDefinition } from "./blocks";
import { LayoutDefinition } from "./layout";
import { NarrationDefinition } from "./narration";
import { NavigationDefinition } from "./navigation";
import { SliceWorkflow } from "./workflow";

export const CourseObjective = z
  .object({ id: objectiveIdSchema, text: z.string().min(1), evidenceBlockIds: z.array(blockIdSchema).min(1) })
  .strict();

const OpeningSignal = z.enum(["recent-course-topics", "prior-objective-performance"]);
export const OpeningDefinition = z
  .object({
    learningPreview: z.array(z.string().min(1)),
    personalization: z.object({ enabled: z.boolean(), allowedSignals: z.array(OpeningSignal) }).strict(),
    fallback: z.object({ text: z.string().min(1), audio: relativeAssetPathSchema.optional() }).strict(),
  })
  .strict();

const ClosingSignal = z.enum(["answers", "attempts", "time-on-slice", "interaction-results"]);
export const ClosingDefinition = z
  .object({
    preparedSummary: z.string().min(1),
    takeaways: z.array(z.string().min(1)),
    transferApplications: z.array(z.string().min(1)),
    personalization: z.object({ enabled: z.boolean(), allowedSignals: z.array(ClosingSignal) }).strict(),
    fallback: z.object({ text: z.string().min(1), audio: relativeAssetPathSchema.optional() }).strict(),
  })
  .strict();

export const SliceDefinition = z
  .object({
    id: sliceIdSchema,
    title: z.string().min(1),
    objectiveIds: z.array(objectiveIdSchema),
    estimatedSeconds: z.number().positive(),
    blocks: z.array(BlockDefinition).min(1),
    layout: LayoutDefinition,
    narrations: z.array(NarrationDefinition),
    workflow: SliceWorkflow,
    navigation: NavigationDefinition,
  })
  .strict();

export const PartDefinition = z
  .object({ id: partIdSchema, title: z.string().min(1), objectiveIds: z.array(objectiveIdSchema), slices: z.array(SliceDefinition).min(1) })
  .strict();

export const CourseDefinition = z
  .object({
    id: courseIdSchema,
    title: z.string().min(1),
    language: z.string().min(2), // BCP-47; deep validation deferred
    estimatedMinutes: z.number().positive(),
    objectives: z.array(CourseObjective).min(1),
    opening: OpeningDefinition,
    parts: z.array(PartDefinition).min(1),
    closing: ClosingDefinition,
  })
  .strict();

export const CourseDefinitionDocument = z.object({ schemaVersion: z.literal("2.0"), course: CourseDefinition }).strict();

export type CourseObjective = z.infer<typeof CourseObjective>;
export type OpeningDefinition = z.infer<typeof OpeningDefinition>;
export type ClosingDefinition = z.infer<typeof ClosingDefinition>;
export type SliceDefinition = z.infer<typeof SliceDefinition>;
export type PartDefinition = z.infer<typeof PartDefinition>;
export type CourseDefinition = z.infer<typeof CourseDefinition>;
export type CourseDefinitionDocument = z.infer<typeof CourseDefinitionDocument>;
