import { useEffect, useRef, useState } from "react";
import { PdfModal } from "./PdfModal";
import type { BlockRenderer, PdfBlock } from "../types";

// Inline "expand / read in popup" glyph — the renderer stays self-contained
// (no icon-library dependency; see package.json deps).
function ExpandIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M15 3h6v6" />
      <path d="M9 21H3v-6" />
      <path d="M21 3l-7 7" />
      <path d="M3 21l7-7" />
    </svg>
  );
}

/** Load lifecycle of the embedded browser PDF viewer. */
type PdfViewState = "loading" | "loaded" | "error";

/**
 * §9.3 / §17.9 — the PDF viewer. Delegates ALL page navigation, zoom, and
 * printing to the browser's own PDF viewer (P1-07 review revision, D2):
 * `pdf.js` and a bespoke page-nav UI added integration/CSP risk for a
 * capability every modern browser already ships behind `<iframe src=".../file.pdf">`.
 * The renderer's job is narrower — resolve the CURRENT signed URL (every
 * render, never captured mount-only, so a refreshed URL is always picked up:
 * P1-11), honor `initialPage` via the `#page=` fragment, show loading/error
 * states around the iframe's own `onLoad`/`onError`, and offer an explicit
 * open-in-new-tab fallback for a browser that can't inline-render.
 *
 * The open links are `target="_blank" rel="noopener noreferrer"` and carry NO
 * `download` attribute: the source is a cross-origin signed CDN URL, for which
 * the browser IGNORES `download` and — worse — drops `target="_blank"`,
 * navigating the CURRENT tab. Since the app has no URL routing, that strands
 * the learner (a "back" click leaves the course for the homepage). A plain
 * new-tab link keeps the course tab intact; the browser's own PDF viewer in
 * the new tab still offers download.
 *
 * It NEVER emits `block.completed`: opening or downloading a PDF is not
 * evidence of reading or understanding (§9.3). Learning evidence comes from a
 * separate assessment or interaction.
 */
export const PdfRenderer: BlockRenderer<PdfBlock> = ({ block, assetResolver, visible, emit }) => {
  // Resolved fresh on every render (never captured in a mount-only effect) so
  // a renewed signed URL is always what the iframe actually points at.
  const url = assetResolver.resolve(block.source);
  const initialPage = block.initialPage ?? 1;
  const iframeSrc = `${url}#page=${initialPage}`;

  const [viewState, setViewState] = useState<PdfViewState>("loading");
  const [expanded, setExpanded] = useState(false);
  const frameRef = useRef<HTMLIFrameElement | null>(null);

  // Mount-once open Event — block identity is stable for a mounted PdfRenderer.
  const emitRef = useRef(emit);
  emitRef.current = emit;
  useEffect(() => {
    emitRef.current(block.id, "pdf.opened", { page: initialPage });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A renewed src (URL refresh, or a different initialPage) mounts a fresh
  // iframe (keyed on iframeSrc below) — reset to "loading" and (re)bind the
  // native `error` listener directly on the element. React does not wire a
  // delegated `onError` for <iframe>/<object>/<embed> — only `onLoad` — so
  // `error` is attached by hand rather than as a JSX prop.
  useEffect(() => {
    setViewState("loading");
    const el = frameRef.current;
    if (!el) return;
    const handleError = () => setViewState("error");
    el.addEventListener("error", handleError);
    return () => el.removeEventListener("error", handleError);
  }, [iframeSrc]);

  return (
    <div
      data-block-id={block.id}
      data-block-type="pdf"
      hidden={!visible}
      aria-hidden={!visible}
      className="course-block course-block--pdf"
    >
      <div className="course-pdf__header">
        <span className="course-pdf__title">{block.title}</span>
        <div className="course-pdf__header-actions">
          <button
            type="button"
            className="course-pdf__expand"
            aria-label={`放大阅读：${block.title}`}
            onClick={() => setExpanded(true)}
          >
            <ExpandIcon />
            放大阅读
          </button>
          <a
            className="course-pdf__download"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => emitRef.current(block.id, "pdf.downloaded", {})}
          >
            在新标签打开
          </a>
        </div>
      </div>
      <div className="course-pdf__viewport" data-pdf-state={viewState}>
        {viewState === "loading" ? (
          <p className="course-pdf__loading" role="status">
            正在加载 PDF…
          </p>
        ) : null}
        {viewState === "error" ? (
          <div className="course-pdf__error" role="alert">
            <p>PDF 加载失败，你的浏览器可能无法内嵌预览这份文件。</p>
            <a className="course-pdf__fallback" href={url} target="_blank" rel="noopener noreferrer">
              在新标签打开
            </a>
          </div>
        ) : (
          <iframe
            key={iframeSrc}
            ref={frameRef}
            className="course-pdf__frame"
            title={block.title}
            src={iframeSrc}
            onLoad={() => setViewState("loaded")}
          />
        )}
      </div>
      {expanded ? <PdfModal src={iframeSrc} title={block.title} onClose={() => setExpanded(false)} /> : null}
    </div>
  );
};
