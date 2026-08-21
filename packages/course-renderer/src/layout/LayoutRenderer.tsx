import type { CSSProperties, ReactNode } from "react";
import type { LayoutDefinition, SplitRatio } from "@mind-imprint/course-contract";

/** Block ids are plain lower-case-hyphenated strings in the contract (no branded type). */
export type BlockId = string;

export interface LayoutRendererProps {
  layout: LayoutDefinition;
  /** Mounts the block renderers for one slot. Supplied by SlicePlayer. */
  renderSlot: (slotId: string, blockIds: BlockId[]) => ReactNode;
}

/**
 * `2:1` → `minmax(0, 2fr) minmax(0, 1fr)`, `3:2` → `minmax(0, 3fr) minmax(0,
 * 2fr)`, etc. A split ratio is always an `"a:b"` pair of positive integer
 * weights (the contract's `SplitRatio` enum bounds the set); parsing it
 * generically means new ratios need no renderer change. §Slice5 / P1-06 —
 * every track is wrapped in `minmax(0, …)` (not a bare `Nfr`) so a track can
 * actually shrink below its content's intrinsic size; a bare `fr` track floors
 * at its content size and blows out the one-screen Slice contract the moment a
 * slot's content is tall/wide. Falls back to 1:1 for a missing/malformed ratio.
 */
function ratioTracks(ratio: SplitRatio | undefined): string {
  const parts = (ratio ?? "1:1").split(":");
  const a = Number.parseInt(parts[0] ?? "1", 10);
  const b = Number.parseInt(parts[1] ?? "1", 10);
  const left = Number.isFinite(a) && a > 0 ? a : 1;
  const right = Number.isFinite(b) && b > 0 ? b : 1;
  return `minmax(0, ${left}fr) minmax(0, ${right}fr)`;
}

/** `n` equal, shrinkable tracks — used when empty slots collapse and the ratio
 * no longer applies (the surviving slots just share the axis evenly). */
function equalTracks(n: number): string {
  return `repeat(${Math.max(1, n)}, minmax(0, 1fr))`;
}

/**
 * §10 / §17.5 — owns only the grid/flex frame that positions slots; the block
 * content is supplied by `renderSlot`. Maps the four presets to stable desktop
 * CSS grid:
 * - `full` → a single `main` region;
 * - `split-horizontal` → two columns from the ratio (`left` | `right`);
 * - `split-vertical` → two rows from the ratio (`top` | `bottom`);
 * - `grid` → a 2-column grid of `cell-1..N`.
 *
 * Every slot that carries blocks is rendered exactly once, in authored order;
 * a slot with zero authored blocks is collapsed (its grid track dropped) so a
 * lopsided split fills the region instead of stranding content in a partial
 * column — see the collapse note in the function body. Hidden blocks inside a
 * *non-empty* slot keep their box (the course stylesheet overrides `[hidden]`
 * to `visibility: hidden` rather than `display: none` — see `styles/course.css`),
 * so revealing a block never reflows its siblings.
 *
 * Slot gaps, per-slot `overflow: auto`, and media containment are the course
 * stylesheet's job (`.course-layout` / `.course-layout__slot` — §Slice5 /
 * P1-06); this component owns only the grid tracks, which vary per preset/
 * ratio and so stay inline.
 */
export function LayoutRenderer({ layout, renderSlot }: LayoutRendererProps) {
  // An empty slot (no *authored* blocks) contributes only dead space. The scene
  // generator routinely emits a lopsided split — e.g. `split-horizontal 3:1`
  // with an empty `right` — which would otherwise strand every block in a
  // partial column beside a blank track, reading as "shoved to one side, not
  // centered." Collapse those: render only the slots that carry blocks and size
  // the grid to them, so a split-with-one-empty-half fills the whole region.
  //
  // "Empty" means zero authored `blockIds` — NOT a slot whose blocks are merely
  // hidden at runtime. A slot with blockIds keeps its box even when every block
  // is `[hidden]` (the stylesheet maps `[hidden]` to `visibility: hidden`), so
  // revealing a block never reflows its siblings; collapsing such a slot would
  // break that guarantee. Runtime hiding never empties `blockIds`, so filtering
  // on `blockIds.length` is safe.
  const filled = layout.slots.filter((slot) => slot.blockIds.length > 0);
  // Degenerate all-empty layout: keep the authored slots so the frame still has
  // its structure rather than collapsing to nothing.
  const slots = filled.length > 0 ? filled : layout.slots;
  const collapsed = slots.length < layout.slots.length;

  const style: CSSProperties = { display: "grid" };
  switch (layout.preset) {
    case "full":
      style.gridTemplateColumns = "minmax(0, 1fr)";
      break;
    case "split-horizontal":
      // With a slot collapsed the ratio no longer maps to two tracks — the
      // survivors share the row evenly (one survivor → a single full-width one).
      style.gridTemplateColumns = collapsed ? equalTracks(slots.length) : ratioTracks(layout.ratio);
      break;
    case "split-vertical":
      style.gridTemplateColumns = "minmax(0, 1fr)";
      style.gridTemplateRows = collapsed ? equalTracks(slots.length) : ratioTracks(layout.ratio);
      break;
    case "grid":
      // A lone surviving cell fills the row instead of clinging to a half-width
      // column; two or more keep the 2-up grid.
      style.gridTemplateColumns = slots.length <= 1 ? "minmax(0, 1fr)" : "repeat(2, minmax(0, 1fr))";
      style.gridAutoRows = "minmax(0, 1fr)";
      break;
  }

  return (
    <div
      className={`course-layout course-layout--${layout.preset}`}
      data-preset={layout.preset}
      data-collapsed={collapsed ? "" : undefined}
      style={style}
    >
      {slots.map((slot) => (
        <div key={slot.id} data-slot={slot.id} className={`course-layout__slot course-layout__slot--${slot.id}`}>
          {renderSlot(slot.id, slot.blockIds)}
        </div>
      ))}
    </div>
  );
}
