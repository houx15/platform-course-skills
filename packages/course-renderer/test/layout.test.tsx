import { render } from "@testing-library/react";
import { LayoutRenderer } from "../src/layout/LayoutRenderer";
import type { LayoutDefinition } from "@mind-imprint/course-contract";

const renderSlot = (slotId: string, blockIds: string[]) => (
  <span data-slot-content={slotId}>{blockIds.join(",")}</span>
);

describe("LayoutRenderer", () => {
  it("full → one region with data-slot='main'", () => {
    const layout: LayoutDefinition = { preset: "full", slots: [{ id: "main", blockIds: ["a"] }] };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const slots = container.querySelectorAll("[data-slot]");
    expect(slots).toHaveLength(1);
    expect(slots[0]).toHaveAttribute("data-slot", "main");
  });

  it("split-horizontal 2:1 → left/right regions with shrinkable minmax(0, …) columns (§Slice5 / P1-06)", () => {
    const layout: LayoutDefinition = {
      preset: "split-horizontal",
      ratio: "2:1",
      slots: [
        { id: "left", blockIds: ["a"] },
        { id: "right", blockIds: ["b"] },
      ],
    };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const frame = container.querySelector("[data-preset]") as HTMLElement;
    expect(frame.style.gridTemplateColumns).toBe("minmax(0, 2fr) minmax(0, 1fr)");
    const ids = [...container.querySelectorAll("[data-slot]")].map((n) => n.getAttribute("data-slot"));
    expect(ids).toEqual(["left", "right"]);
  });

  it("split-horizontal 3:2 → weighted columns (60/40) via generic ratio parsing", () => {
    const layout: LayoutDefinition = {
      preset: "split-horizontal",
      ratio: "3:2",
      slots: [
        { id: "left", blockIds: ["a"] },
        { id: "right", blockIds: ["b"] },
      ],
    };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const frame = container.querySelector("[data-preset]") as HTMLElement;
    expect(frame.style.gridTemplateColumns).toBe("minmax(0, 3fr) minmax(0, 2fr)");
  });

  it("split-vertical 1:3 → strongly weighted rows (25/75)", () => {
    const layout: LayoutDefinition = {
      preset: "split-vertical",
      ratio: "1:3",
      slots: [
        { id: "top", blockIds: ["a"] },
        { id: "bottom", blockIds: ["b"] },
      ],
    };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const frame = container.querySelector("[data-preset]") as HTMLElement;
    expect(frame.style.gridTemplateRows).toBe("minmax(0, 1fr) minmax(0, 3fr)");
  });

  it("split-vertical 1:2 → top/bottom regions with shrinkable minmax(0, …) rows (§Slice5 / P1-06)", () => {
    const layout: LayoutDefinition = {
      preset: "split-vertical",
      ratio: "1:2",
      slots: [
        { id: "top", blockIds: ["a"] },
        { id: "bottom", blockIds: ["b"] },
      ],
    };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const frame = container.querySelector("[data-preset]") as HTMLElement;
    expect(frame.style.gridTemplateRows).toBe("minmax(0, 1fr) minmax(0, 2fr)");
    const ids = [...container.querySelectorAll("[data-slot]")].map((n) => n.getAttribute("data-slot"));
    expect(ids).toEqual(["top", "bottom"]);
  });

  it("grid with 3 cells → cell-1..3 each appearing once, with shrinkable minmax(0, …) tracks (§Slice5 / P1-06)", () => {
    const layout: LayoutDefinition = {
      preset: "grid",
      slots: [
        { id: "cell-1", blockIds: ["a"] },
        { id: "cell-2", blockIds: ["b"] },
        { id: "cell-3", blockIds: ["c"] },
      ],
    };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const ids = [...container.querySelectorAll("[data-slot]")].map((n) => n.getAttribute("data-slot"));
    expect(ids).toEqual(["cell-1", "cell-2", "cell-3"]);
    const frame = container.querySelector("[data-preset]") as HTMLElement;
    expect(frame.style.gridTemplateColumns).toBe("repeat(2, minmax(0, 1fr))");
    expect(frame.style.gridAutoRows).toBe("minmax(0, 1fr)");
  });

  it("every slot is a contained overflow container, never the page (§Slice5 / P1-06)", () => {
    const layout: LayoutDefinition = { preset: "full", slots: [{ id: "main", blockIds: ["a"] }] };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    const slot = container.querySelector('[data-slot="main"]') as HTMLElement;
    expect(slot).toHaveClass("course-layout__slot");
  });

  it("passes each slot's blockIds to renderSlot", () => {
    const layout: LayoutDefinition = { preset: "full", slots: [{ id: "main", blockIds: ["a", "b"] }] };
    const { container } = render(<LayoutRenderer layout={layout} renderSlot={renderSlot} />);
    expect(container.querySelector('[data-slot-content="main"]')).toHaveTextContent("a,b");
  });
});
