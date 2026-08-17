import { render, screen } from "@testing-library/react";
import { TextRenderer } from "../src/blocks/TextRenderer";
import type { TextBlock } from "../src/blocks/types";
import type { AssetResolver, SliceEmitter } from "@mind-imprint/course-runtime";

const assetResolver: AssetResolver = { resolve: (p) => `/resolved/${p}` };
const emit: SliceEmitter = () => {};

function renderText(content: string, visible = true) {
  const block = { id: "intro", type: "text", content } as unknown as TextBlock;
  return render(
    <TextRenderer
      block={block}
      assetResolver={assetResolver}
      state={{ visible, enabled: true, completed: false }}
      visible={visible}
      enabled
      emit={emit}
    />,
  );
}

describe("TextRenderer", () => {
  it("renders restricted markdown (**bold** → <strong>)", () => {
    renderText("Hello **world**");
    const strong = screen.getByText("world");
    expect(strong.tagName).toBe("STRONG");
  });

  it("does not render raw <script> as an element", () => {
    const { container } = renderText("before <script>alert(1)</script> after");
    expect(container.querySelector("script")).toBeNull();
  });

  it("does not render raw <iframe> as an element", () => {
    const { container } = renderText("look <iframe src='https://evil.example'></iframe>");
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("hidden block keeps its slot but is aria-hidden/hidden", () => {
    const { container } = renderText("secret", false);
    const wrapper = container.querySelector('[data-block-id="intro"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveAttribute("aria-hidden", "true");
    expect(wrapper).toHaveAttribute("hidden");
  });
});
