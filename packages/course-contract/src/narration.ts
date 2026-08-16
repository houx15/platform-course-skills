import { z } from "zod";
import { narrationIdSchema, relativeAssetPathSchema } from "./primitives";

export const NarrationDefinition = z
  .object({ id: narrationIdSchema, text: z.string().min(1), audio: relativeAssetPathSchema, durationSeconds: z.number().positive().optional() })
  .strict();

export type NarrationDefinition = z.infer<typeof NarrationDefinition>;
