import { z } from "zod";
import { blockIdSchema } from "./primitives";

export const LayoutPreset = z.enum(["full", "split-horizontal", "split-vertical", "grid"]);
// Split weights for the two tracks of a split-horizontal/-vertical layout.
// Symmetric set: balanced (1:1), gently weighted (3:2 / 2:3), weighted
// (2:1 / 1:2), and strongly weighted (3:1 / 1:3). Bounded on purpose — the
// most lopsided is 3:1, so neither side is ever thinner than a quarter.
export const SplitRatio = z.enum(["1:1", "3:2", "2:3", "2:1", "1:2", "3:1", "1:3"]);

export const LayoutSlot = z.object({ id: z.string().min(1), blockIds: z.array(blockIdSchema) }).strict();

const GRID_CELL_IDS = ["cell-1", "cell-2", "cell-3", "cell-4"] as const;

export const LayoutDefinition = z
  .object({ preset: LayoutPreset, ratio: SplitRatio.optional(), slots: z.array(LayoutSlot).min(1) })
  .strict()
  .superRefine((layout, ctx) => {
    const ids = layout.slots.map((s) => s.id);
    const has = (want: string[]) => want.length === ids.length && want.every((w) => ids.includes(w));
    switch (layout.preset) {
      case "full":
        if (!has(["main"])) ctx.addIssue({ code: "custom", message: "full layout requires exactly one slot 'main'" });
        break;
      case "split-horizontal":
        if (!layout.ratio) ctx.addIssue({ code: "custom", message: "split-horizontal requires a ratio" });
        if (!has(["left", "right"])) ctx.addIssue({ code: "custom", message: "split-horizontal requires slots 'left' and 'right'" });
        break;
      case "split-vertical":
        if (!layout.ratio) ctx.addIssue({ code: "custom", message: "split-vertical requires a ratio" });
        if (!has(["top", "bottom"])) ctx.addIssue({ code: "custom", message: "split-vertical requires slots 'top' and 'bottom'" });
        break;
      case "grid": {
        const n = ids.length;
        const canonical = n >= 2 && n <= 4 && ids.every((id, i) => id === GRID_CELL_IDS[i]);
        if (!canonical) ctx.addIssue({ code: "custom", message: "grid requires 2–4 slots named cell-1..cell-N in order" });
        break;
      }
    }
  });

export type LayoutPreset = z.infer<typeof LayoutPreset>;
export type SplitRatio = z.infer<typeof SplitRatio>;
export type LayoutSlot = z.infer<typeof LayoutSlot>;
export type LayoutDefinition = z.infer<typeof LayoutDefinition>;
