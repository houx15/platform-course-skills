import { render, screen } from "@testing-library/react";
import { RichTextRenderer, buildRichTextDocument } from "../src/blocks/RichTextRenderer";
import { getBlockRenderer } from "../src/blocks/registry";
import type { RichTextBlock } from "../src/blocks/types";
import type { AssetResolver, SliceEmitter } from "@mind-imprint/course-runtime";

const assetResolver: AssetResolver = { resolve: (p) => `/resolved/${p}` };
const emit: SliceEmitter = () => {};

function renderCard(html: string, opts: { visible?: boolean; title?: string } = {}) {
  const visible = opts.visible ?? true;
  const block = { id: "card", type: "richText", html, ...(opts.title ? { title: opts.title } : {}) } as unknown as RichTextBlock;
  const result = render(
    <RichTextRenderer
      block={block}
      assetResolver={assetResolver}
      state={{ visible, enabled: true, completed: false }}
      visible={visible}
      enabled
      emit={emit}
    />,
  );
  const frame = result.container.querySelector("iframe") as HTMLIFrameElement | null;
  return { ...result, frame };
}

describe("RichTextRenderer", () => {
  it("is the registered renderer for the richText block type", () => {
    expect(getBlockRenderer("richText")).toBe(RichTextRenderer);
  });

  it("renders the authored html inside a frame fed by srcdoc, never a URL — that is what makes it OSS-free", () => {
    const { frame } = renderCard("<h2>三种来源</h2>");
    expect(frame).not.toBeNull();
    expect(frame!.getAttribute("srcdoc")).toContain("<h2>三种来源</h2>");
    expect(frame!.hasAttribute("src")).toBe(false);
  });

  it("sandboxes WITHOUT allow-scripts or allow-same-origin — the browser, not a denylist, makes authored markup inert", () => {
    const { frame } = renderCard("<p>hi</p>");
    const sandbox = frame!.getAttribute("sandbox") ?? "";
    expect(sandbox).not.toContain("allow-scripts");
    expect(sandbox).not.toContain("allow-same-origin");
    // Links still open: with no scripts, a popup can only come from a click.
    expect(sandbox).toContain("allow-popups");
  });

  it("keeps authored <style> inside the frame, so a course can never restyle the app", () => {
    const { container, frame } = renderCard("<style>body{color:red}</style><p>hi</p>");
    // The style lives in the srcdoc string, NOT in the host document.
    expect(frame!.getAttribute("srcdoc")).toContain("body{color:red}");
    expect(container.querySelector("style")).toBeNull();
  });

  it("prepends base typography the author can override — their <style> comes last", () => {
    const doc = buildRichTextDocument("<style>h2{font-size:99px}</style><h2>x</h2>", "--course-ink: #111;");
    expect(doc.indexOf("line-height")).toBeLessThan(doc.indexOf("font-size:99px"));
    expect(doc).toContain("--course-ink: #111;");
  });

  it("names the frame for screen readers, from the authored title when given", () => {
    renderCard("<p>hi</p>", { title: "来源类型对照" });
    expect(screen.getByTitle("来源类型对照")).not.toBeNull();
    renderCard("<p>hi</p>");
    expect(screen.getAllByTitle("图文卡片").length).toBeGreaterThan(0);
  });

  it("hidden block keeps its box but is hidden/aria-hidden (§10)", () => {
    const { container } = renderCard("<p>secret</p>", { visible: false });
    const wrapper = container.querySelector('[data-block-id="card"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveAttribute("hidden");
    expect(wrapper).toHaveAttribute("aria-hidden", "true");
  });

  it("keeps a stable srcdoc across unrelated re-renders — a reload would throw away the student's scroll position", () => {
    const block = { id: "card", type: "richText", html: "<p>long read</p>" } as unknown as RichTextBlock;
    const props = {
      block,
      assetResolver,
      state: { visible: true, enabled: true, completed: false },
      visible: true,
      enabled: true,
      emit,
    };
    const { container, rerender } = render(<RichTextRenderer {...props} />);
    const before = container.querySelector("iframe")!.getAttribute("srcdoc");
    rerender(<RichTextRenderer {...props} enabled={false} />);
    expect(container.querySelector("iframe")!.getAttribute("srcdoc")).toBe(before);
  });
});
