import { z } from "zod";

export const NavigationDefinition = z
  .object({
    previous: z.literal("allowed"),
    manualNext: z.enum(["after-completion", "allowed"]),
    autoNext: z.boolean(),
    revisit: z.literal("restore-completed-state"),
  })
  .strict();

export type NavigationDefinition = z.infer<typeof NavigationDefinition>;
