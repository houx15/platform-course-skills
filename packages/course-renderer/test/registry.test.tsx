import { render } from "@testing-library/react";
import { BlockDefinition } from "@mind-imprint/course-contract";
import { getBlockRenderer, blockRenderers } from "../src/blocks/registry";
import { NotImplementedRenderer } from "../src/blocks/NotImplementedRenderer";
import type { AssetResolver, SliceEmitter } from "@mind-imprint/course-runtime";

const assetResolver: AssetResolver = { resolve: (p) => `/resolved/${p}` };
const emit: SliceEmitter = () => {};

// Every `type` literal in the BlockDefinition discriminated union.
const CONTRACT_BLOCK_TYPES: string[] = BlockDefinition.options.map(
  (member: any) => member.shape.type.value as string,
);

describe("block registry", () => {
  it("returns a component for a built-in type", () => {
    const R = getBlockRenderer("text");
    expect(typeof R).toBe("function");
  });

  it("maps every block type to a real renderer — zero NotImplemented entries remain", () => {
    for (const type of CONTRACT_BLOCK_TYPES) {
      expect(getBlockRenderer(type)).not.toBe(NotImplementedRenderer);
    }
  });

  it("throws for an unregistered block type (fail before playback)", () => {
    expect(() => getBlockRenderer("carousel")).toThrow();
  });

  // Derived from the CONTRACT, not a hand-kept list: adding a block type to the
  // union without registering a renderer must fail here, and the count must
  // never need editing again.
  it("registry is total over every block type the contract defines", () => {
    expect(Object.keys(blockRenderers).sort()).toEqual([...CONTRACT_BLOCK_TYPES].sort());
  });

  it("NotImplementedRenderer renders a labelled data-block-type box", () => {
    const R = NotImplementedRenderer;
    const { container } = render(
      <R
        block={{ id: "h1", type: "interactiveHtml", source: "assets/h.html", protocolVersion: "1.0", aspectRatio: "4:3" } as any}
        assetResolver={assetResolver}
        state={{ visible: true, enabled: true, completed: false }}
        visible
        enabled
        emit={emit}
      />,
    );
    const box = container.querySelector('[data-not-implemented="true"]');
    expect(box).not.toBeNull();
    expect(box).toHaveAttribute("data-block-type", "interactiveHtml");
  });
});
