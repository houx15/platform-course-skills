import type { ComponentType } from "react";
import type { BlockDefinition, BlockSessionState } from "@mind-imprint/course-contract";
import type { AssetResolver, SliceEmitter } from "@mind-imprint/course-runtime";

/**
 * §17.6 — the props every block renderer receives. Renderers are pure: all
 * side-effecting seams arrive through props.
 *
 * - `assetResolver` maps authored relative paths → resolvable URLs (Slice 2).
 * - `state` is the block's persisted `BlockSessionState`.
 * - `visible`/`enabled` are the live layout flags; a hidden block keeps its slot
 *   (§10) rather than unmounting.
 * - `focusedItemId` is set when a `focus` targets an item inside this block.
 * - `emit` is the slice-scoped bus emitter; the block passes its own id as
 *   `sourceId`. It is exactly the runtime's {@link SliceEmitter}, so its `type`
 *   argument accepts both the standardized `WorkflowEventType`s and renderer
 *   signals like `image.selected` (`CourseRuntimeEvent["type"]`).
 */
export interface BlockRendererProps<TBlock extends BlockDefinition = BlockDefinition> {
  block: TBlock;
  assetResolver: AssetResolver;
  state: BlockSessionState;
  visible: boolean;
  enabled: boolean;
  focusedItemId?: string;
  emit: SliceEmitter;
}

export type BlockRenderer<TBlock extends BlockDefinition = BlockDefinition> = ComponentType<BlockRendererProps<TBlock>>;

/**
 * The contract exports each block's Zod schema as a value only (`BlockDefinition`
 * is the sole exported union type). These narrow the union by discriminant so
 * renderers and their tests can name a concrete block shape.
 */
export type TextBlock = Extract<BlockDefinition, { type: "text" }>;
export type RichTextBlock = Extract<BlockDefinition, { type: "richText" }>;
export type ImagesBlock = Extract<BlockDefinition, { type: "images" }>;
export type ImageItem = ImagesBlock["items"][number];
export type FillBlankBlock = Extract<BlockDefinition, { type: "fillBlank" }>;
export type SingleChoiceBlock = Extract<BlockDefinition, { type: "singleChoice" }>;
export type VideoBlock = Extract<BlockDefinition, { type: "video" }>;
export type PdfBlock = Extract<BlockDefinition, { type: "pdf" }>;
export type InteractiveHtmlBlock = Extract<BlockDefinition, { type: "interactiveHtml" }>;
