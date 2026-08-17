import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { BlockRenderer, TextBlock } from "./types";

/**
 * §9.1 / §17.7 — renders a text block's restricted Markdown.
 *
 * SECURITY: no `rehype-raw`. react-markdown escapes embedded raw HTML by
 * default, so an authored `<script>` / `<iframe>` is rendered as inert text,
 * never as a live DOM element. Only GitHub-flavoured Markdown (tables, etc.) is
 * enabled via `remark-gfm`.
 *
 * §10 — a hidden block keeps its layout slot: we render the content but mark the
 * wrapper `hidden` + `aria-hidden` rather than unmounting, so revealing it later
 * does not reflow siblings.
 */
export const TextRenderer: BlockRenderer<TextBlock> = ({ block, visible }) => (
  <div
    data-block-id={block.id}
    data-block-type="text"
    hidden={!visible}
    aria-hidden={!visible}
    className="course-block course-block--text prose"
  >
    <Markdown remarkPlugins={[remarkGfm]}>{block.content}</Markdown>
  </div>
);
