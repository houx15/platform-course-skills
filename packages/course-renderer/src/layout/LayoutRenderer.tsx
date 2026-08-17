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
 * `2:1` → `minmax(0, 2fr) minmax(0, 1fr)` etc. Split ratios only ever have two
 * tracks. §Slice5 / P1-06 — every track is wrapped in `minmax(0, …)` (not a
 * bare `Nfr`) so a track can actually shrink below its content's intrinsic
 * size; a bare `fr` track floors at its content size and blows out the
 * one-screen Slice contract the moment a slot's content is tall/wide.
 */
function ratioTracks(ratio: SplitRatio | undefined): string {
  switch (ratio) {
    case "2:1":
      return "minmax(0, 2fr) minmax(0, 1fr)";
    case "1:2":
      return "minmax(0, 1fr) minmax(0, 2fr)";
    case "1:1":
    default:
      return "minmax(0, 1fr) minmax(0, 1fr)";
  }
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
 * Every slot in the layout is rendered exactly once, in authored order. Hidden
 * blocks inside a slot keep their box (the course stylesheet overrides
 * `[hidden]` to `visibility: hidden` rather than `display: none` — see
 * `styles/course.css`), so revealing a block never reflows its siblings.
 *
 * Slot gaps, per-slot `overflow: auto`, and media containment are the course
 * stylesheet's job (`.course-layout` / `.course-layout__slot` — §Slice5 /
 * P1-06); this component owns only the grid tracks, which vary per preset/
 * ratio and so stay inline.
 */
export function LayoutRenderer({ layout, renderSlot }: LayoutRendererProps) {
  const style: CSSProperties = { display: "grid" };
  switch (layout.preset) {
    case "full":
      style.gridTemplateColumns = "minmax(0, 1fr)";
      break;
    case "split-horizontal":
      style.gridTemplateColumns = ratioTracks(layout.ratio);
      break;
    case "split-vertical":
      style.gridTemplateRows = ratioTracks(layout.ratio);
      style.gridTemplateColumns = "minmax(0, 1fr)";
      break;
    case "grid":
      style.gridTemplateColumns = "repeat(2, minmax(0, 1fr))";
      style.gridAutoRows = "minmax(0, 1fr)";
      break;
  }

  return (
    <div className={`course-layout course-layout--${layout.preset}`} data-preset={layout.preset} style={style}>
      {layout.slots.map((slot) => (
        <div key={slot.id} data-slot={slot.id} className={`course-layout__slot course-layout__slot--${slot.id}`}>
          {renderSlot(slot.id, slot.blockIds)}
        </div>
      ))}
    </div>
  );
}
