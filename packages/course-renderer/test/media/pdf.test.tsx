import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BlockSessionState } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";
import { PdfRenderer } from "../../src/blocks/media/PdfRenderer";
import type { PdfBlock } from "../../src/blocks/types";

interface Recorded {
  sourceId: string;
  type: string;
  payload: unknown;
}

const pdfBlock: PdfBlock = {
  id: "source-paper",
  type: "pdf",
  title: "Original Research Paper",
  source: "assets/pdfs/source-paper.pdf",
  initialPage: 3,
};

function renderPdf(block: PdfBlock = pdfBlock, resolve: (p: string) => string = (p) => `/resolved/${p}`) {
  const events: Recorded[] = [];
  const emit: SliceEmitter = (sourceId, type, payload) => events.push({ sourceId, type: String(type), payload });
  const assetResolver = { resolve };
  const baseState: BlockSessionState = { visible: true, enabled: true, completed: false };
  const utils = render(
    <PdfRenderer block={block} assetResolver={assetResolver} state={baseState} visible enabled emit={emit} />,
  );
  return { ...utils, events, assetResolver };
}

const typeNames = (events: Recorded[]) => events.map((e) => e.type);

describe("PdfRenderer", () => {
  it("emits pdf.opened on first view and renders the resolved URL, honoring initialPage via #page=", () => {
    const { events, container } = renderPdf();
    expect(typeNames(events)).toContain("pdf.opened");
    const iframe = container.querySelector<HTMLIFrameElement>("iframe.course-pdf__frame")!;
    expect(iframe).toHaveAttribute("src", "/resolved/assets/pdfs/source-paper.pdf#page=3");
  });

  it("defaults initialPage to 1 when the block doesn't specify one", () => {
    const { container } = renderPdf({ ...pdfBlock, initialPage: undefined });
    const iframe = container.querySelector<HTMLIFrameElement>("iframe.course-pdf__frame")!;
    expect(iframe).toHaveAttribute("src", "/resolved/assets/pdfs/source-paper.pdf#page=1");
  });

  it("renders inside a sized, slot-contained viewport (P1-07)", () => {
    const { container } = renderPdf();
    const viewport = container.querySelector(".course-pdf__viewport");
    expect(viewport).not.toBeNull();
    const iframe = container.querySelector("iframe.course-pdf__frame");
    expect(viewport?.contains(iframe)).toBe(true);
  });

  it("shows a loading state until the iframe fires onLoad, then clears it", () => {
    const { container } = renderPdf();
    expect(container.querySelector(".course-pdf__loading")).not.toBeNull();
    const iframe = container.querySelector("iframe.course-pdf__frame")!;
    fireEvent.load(iframe);
    expect(container.querySelector(".course-pdf__loading")).toBeNull();
  });

  it("shows an error state + download/open fallback on load failure", () => {
    const { container } = renderPdf();
    const iframe = container.querySelector("iframe.course-pdf__frame")!;
    fireEvent.error(iframe);
    expect(container.querySelector(".course-pdf__error")).not.toBeNull();
    expect(container.querySelector("iframe.course-pdf__frame")).toBeNull();
    const fallback = container.querySelector("a.course-pdf__fallback")!;
    expect(fallback).toHaveAttribute("href", "/resolved/assets/pdfs/source-paper.pdf");
    expect(fallback).toHaveAttribute("target", "_blank");
  });

  it("always offers an explicit open-in-new-tab link in the header", () => {
    const { container } = renderPdf();
    const link = container.querySelector("a.course-pdf__download")!;
    expect(link).toHaveAttribute("href", "/resolved/assets/pdfs/source-paper.pdf");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("the open link forces a NEW tab and carries no `download` attr — a cross-origin URL must never hijack the current tab (no URL routing → 'back' would leave the course)", () => {
    const { container } = renderPdf();
    for (const sel of ["a.course-pdf__download"]) {
      const link = container.querySelector(sel)!;
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).not.toHaveAttribute("download");
      expect(link.getAttribute("rel")).toContain("noopener");
    }
    // error-state fallback link too
    const iframe = container.querySelector("iframe.course-pdf__frame")!;
    fireEvent.error(iframe);
    const fallback = container.querySelector("a.course-pdf__fallback")!;
    expect(fallback).toHaveAttribute("target", "_blank");
    expect(fallback).not.toHaveAttribute("download");
    expect(fallback.getAttribute("rel")).toContain("noopener");
  });

  it("clicking download emits pdf.downloaded", async () => {
    const user = userEvent.setup();
    const { events, container } = renderPdf();
    const link = container.querySelector("a.course-pdf__download")!;
    await user.click(link);
    expect(typeNames(events)).toContain("pdf.downloaded");
  });

  it("NEVER emits block.completed (opening/downloading is not learning completion, §9.3)", async () => {
    const user = userEvent.setup();
    const { events, container } = renderPdf();
    const iframe = container.querySelector("iframe.course-pdf__frame")!;
    fireEvent.load(iframe);
    await user.click(container.querySelector("a.course-pdf__download")!);
    expect(typeNames(events)).not.toContain("block.completed");
  });

  it("放大阅读 opens a modal reading the same document; Esc closes it", async () => {
    const user = userEvent.setup();
    renderPdf();
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: /放大阅读/ }));
    const dialog = screen.getByRole("dialog");
    const modalFrame = dialog.querySelector<HTMLIFrameElement>("iframe.course-pdf-modal__frame");
    expect(modalFrame).toHaveAttribute("src", "/resolved/assets/pdfs/source-paper.pdf#page=3");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clicking the PDF modal backdrop closes it", async () => {
    const user = userEvent.setup();
    renderPdf();
    await user.click(screen.getByRole("button", { name: /放大阅读/ }));
    const backdrop = document.querySelector(".course-pdf-modal__backdrop");
    expect(backdrop).toBeTruthy();
    await user.click(backdrop as Element);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("no bespoke page-nav controls remain (the browser viewer owns paging/zoom)", () => {
    const { container } = renderPdf();
    expect(screen.queryByRole("button", { name: "上一页" })).toBeNull();
    expect(screen.queryByRole("button", { name: "下一页" })).toBeNull();
    expect(container.querySelector(".course-pdf__nav")).toBeNull();
  });

  it("picks up a renewed URL on re-render — never holds a stale resolved URL", () => {
    let current = "/resolved/v1.pdf";
    const { container, rerender } = render(
      <PdfRenderer
        block={pdfBlock}
        assetResolver={{ resolve: () => current }}
        state={{ visible: true, enabled: true, completed: false }}
        visible
        enabled
        emit={() => {}}
      />,
    );
    expect(container.querySelector("iframe.course-pdf__frame")).toHaveAttribute("src", "/resolved/v1.pdf#page=3");

    current = "/resolved/v2-renewed.pdf";
    rerender(
      <PdfRenderer
        block={pdfBlock}
        assetResolver={{ resolve: () => current }}
        state={{ visible: true, enabled: true, completed: false }}
        visible
        enabled
        emit={() => {}}
      />,
    );
    expect(container.querySelector("iframe.course-pdf__frame")).toHaveAttribute(
      "src",
      "/resolved/v2-renewed.pdf#page=3",
    );
  });
});
