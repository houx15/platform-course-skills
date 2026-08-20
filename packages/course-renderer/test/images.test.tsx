import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ImagesRenderer } from "../src/blocks/ImagesRenderer";
import type { ImagesBlock } from "../src/blocks/types";
import type { AssetResolver, SliceEmitter } from "@mind-imprint/course-runtime";

const assetResolver: AssetResolver = { resolve: (p) => `/resolved/${p}` };

function renderImages(block: ImagesBlock, opts: { emit?: SliceEmitter; focusedItemId?: string } = {}) {
  const emit = opts.emit ?? (() => {});
  return render(
    <ImagesRenderer
      block={block}
      assetResolver={assetResolver}
      state={{ visible: true, enabled: true, completed: false }}
      visible
      enabled
      focusedItemId={opts.focusedItemId}
      emit={emit}
    />,
  );
}

const block = (presentation: ImagesBlock["presentation"], n: number): ImagesBlock => ({
  id: "pics",
  type: "images",
  presentation,
  items: Array.from({ length: n }, (_, i) => ({ id: `item-${i + 1}`, source: `img/${i + 1}.png`, alt: `alt ${i + 1}` })),
});

describe("ImagesRenderer", () => {
  it("single renders one <img> with resolved src + alt", () => {
    const { container } = renderImages(block("single", 3));
    const imgs = container.querySelectorAll("img");
    expect(imgs).toHaveLength(1);
    expect(imgs[0]).toHaveAttribute("src", "/resolved/img/1.png");
    expect(imgs[0]).toHaveAttribute("alt", "alt 1");
  });

  it("side-by-side renders two images", () => {
    const { container } = renderImages(block("side-by-side", 2));
    expect(container.querySelectorAll("img")).toHaveLength(2);
  });

  it("gallery shows one item and firing next emits image.selected with the new item id", async () => {
    const user = userEvent.setup();
    const events: Array<{ sourceId: string; type: string; payload: unknown }> = [];
    const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
    renderImages(block("gallery", 3), { emit });

    // one image visible at a time
    expect(screen.getAllByRole("img")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "下一张" }));
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ sourceId: "pics", type: "image.selected", payload: { itemId: "item-2" } });
  });

  it("focusedItemId marks the matching item", () => {
    const { container } = renderImages(block("side-by-side", 2), { focusedItemId: "item-2" });
    const focused = container.querySelectorAll('[data-focused="true"]');
    expect(focused).toHaveLength(1);
    expect(focused[0]).toHaveAttribute("data-item-id", "item-2");
  });

  it("clicking a figure opens the lightbox with the enlarged image + caption", async () => {
    const user = userEvent.setup();
    const withCaption: ImagesBlock = {
      id: "pics",
      type: "images",
      presentation: "single",
      items: [{ id: "item-1", source: "img/1.png", alt: "alt 1", caption: "一张示意图" }],
    };
    renderImages(withCaption);
    // no lightbox until clicked
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: /放大图片/ }));

    const dialog = screen.getByRole("dialog");
    const big = dialog.querySelector("img.course-lightbox__img");
    expect(big).toHaveAttribute("src", "/resolved/img/1.png");
    expect(dialog).toHaveTextContent("一张示意图");
  });

  it("Escape closes the lightbox", async () => {
    const user = userEvent.setup();
    renderImages(block("single", 1));
    await user.click(screen.getByRole("button", { name: /放大图片/ }));
    expect(screen.getByRole("dialog")).toBeTruthy();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clicking the backdrop closes the lightbox", async () => {
    const user = userEvent.setup();
    renderImages(block("single", 1));
    await user.click(screen.getByRole("button", { name: /放大图片/ }));

    const backdrop = document.querySelector(".course-lightbox__backdrop");
    expect(backdrop).toBeTruthy();
    await user.click(backdrop as Element);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  // P1-11: unlike video/iframe, swapping an image's src on a signed-URL
  // refresh is cheap/harmless (no playback or interaction state to lose) —
  // it's fine, and expected, for it to stay live across a re-render.
  it("picks up a renewed URL on re-render (P1-11 — harmless for images)", () => {
    let current = "/resolved/img/1.png";
    const resolver = { resolve: () => current };
    const oneItem: ImagesBlock = {
      id: "pics",
      type: "images",
      presentation: "single",
      items: [{ id: "item-1", source: "img/1.png", alt: "alt 1" }],
    };
    // A FRESH element each call (not a cached, reused JSX reference) — see
    // the equivalent note in video.test.tsx/htmlInteraction.test.tsx: a real
    // parent state update always produces new props objects for its
    // subtree, so reusing one element across `rerender()` would let React
    // bail via prop-identity and never actually re-invoke this component.
    const buildUi = () => (
      <ImagesRenderer
        block={oneItem}
        assetResolver={resolver}
        state={{ visible: true, enabled: true, completed: false }}
        visible
        enabled
        emit={() => {}}
      />
    );
    const { container, rerender } = render(buildUi());
    expect(container.querySelector("img")).toHaveAttribute("src", "/resolved/img/1.png");

    current = "/resolved/img/1-renewed.png";
    rerender(buildUi());

    expect(container.querySelector("img")).toHaveAttribute("src", "/resolved/img/1-renewed.png");
  });
});
