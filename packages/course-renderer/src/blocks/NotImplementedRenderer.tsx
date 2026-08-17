import type { BlockRenderer } from "./types";

/**
 * Placeholder for block types not yet built in this slice (pdf/video → Slice 5,
 * fillBlank/singleChoice → Slice 4, interactiveHtml → Slice 6). Keeps the
 * registry total so `getBlockRenderer` never fails at lookup for a known type;
 * later slices replace the registration with the real renderer.
 */
export const NotImplementedRenderer: BlockRenderer = ({ block, visible }) => (
  <div
    data-block-id={block.id}
    data-block-type={block.type}
    data-not-implemented="true"
    role="note"
    hidden={!visible}
    aria-hidden={!visible}
    className="course-block course-block--not-implemented"
  >
    此内容块类型（{block.type}）尚未支持。
  </div>
);
