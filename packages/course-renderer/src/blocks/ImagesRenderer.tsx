import { useState } from "react";
import type { BlockRenderer, BlockRendererProps, ImageItem, ImagesBlock } from "./types";

function Figure({
  item,
  assetResolver,
  focused,
}: {
  item: ImageItem;
  assetResolver: BlockRendererProps<ImagesBlock>["assetResolver"];
  focused: boolean;
}) {
  return (
    <figure
      data-item-id={item.id}
      data-focused={focused ? "true" : undefined}
      className={`course-images__item${focused ? " is-focused" : ""}`}
    >
      <img src={assetResolver.resolve(item.source)} alt={item.alt} />
      {item.caption ? <figcaption>{item.caption}</figcaption> : null}
    </figure>
  );
}

/**
 * §9.2 / §17.8 — renders an images block in one of three presentations.
 * `single` shows the first item; `side-by-side` shows all items in a row;
 * `gallery` shows one item at a time with prev/next navigation.
 *
 * On a gallery change we emit `image.selected` with the new item id (§9.2 — a
 * gallery emits selection but never a completion event). Item paths are resolved
 * through the injected `assetResolver`; the renderer never builds URLs itself.
 * A `focusedItemId` marks the matching item with `data-focused`.
 */
export const ImagesRenderer: BlockRenderer<ImagesBlock> = ({ block, assetResolver, visible, focusedItemId, emit }) => {
  const [activeIndex, setActiveIndex] = useState(0);
  const items = block.items;

  const wrapperProps = {
    "data-block-id": block.id,
    "data-block-type": "images" as const,
    "data-presentation": block.presentation,
    hidden: !visible,
    "aria-hidden": !visible,
    className: "course-block course-block--images",
  };

  if (block.presentation === "gallery") {
    const safeIndex = Math.min(activeIndex, items.length - 1);
    const active = items[safeIndex]!;
    const goTo = (index: number) => {
      const next = (index + items.length) % items.length;
      setActiveIndex(next);
      emit(block.id, "image.selected", { itemId: items[next]!.id });
    };
    return (
      <div {...wrapperProps}>
        <div className="course-images__gallery" role="group" aria-label="图片画廊">
          <Figure item={active} assetResolver={assetResolver} focused={active.id === focusedItemId} />
          <div className="course-images__nav">
            <button type="button" data-nav="prev" aria-label="上一张" onClick={() => goTo(safeIndex - 1)}>
              上一张
            </button>
            <span data-gallery-position aria-hidden="true">
              {safeIndex + 1} / {items.length}
            </span>
            <button type="button" data-nav="next" aria-label="下一张" onClick={() => goTo(safeIndex + 1)}>
              下一张
            </button>
          </div>
        </div>
      </div>
    );
  }

  const shown = block.presentation === "single" ? items.slice(0, 1) : items;
  return (
    <div {...wrapperProps}>
      <div className={`course-images__${block.presentation}`}>
        {shown.map((item) => (
          <Figure key={item.id} item={item} assetResolver={assetResolver} focused={item.id === focusedItemId} />
        ))}
      </div>
    </div>
  );
};
