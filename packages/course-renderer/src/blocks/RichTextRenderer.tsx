import { useMemo, useRef } from "react";
import type { BlockRenderer, RichTextBlock } from "./types";

/**
 * §9.x / §17.7 — renders a `richText` block: authored, STATIC HTML+CSS shown as
 * a scrollable card that fills its slot.
 *
 * WHY AN IFRAME, not `dangerouslySetInnerHTML` + a sanitizer. Two independent
 * reasons, either one sufficient:
 *
 *  1. **Style isolation.** The whole point of this block is authored CSS. Inject
 *     an authored `<style>` into the app's own document and its selectors apply
 *     to the ENTIRE app — one course could restyle the nav. A sanitizer that
 *     strips `<style>` would delete the feature; one that rewrites selectors to
 *     scope them is a CSS parser we would have to keep correct forever. A
 *     separate document scopes it for free, exactly.
 *  2. **No execution.** The sandbox omits `allow-scripts`, so scripts, inline
 *     handlers and `javascript:` URLs do not run — the browser enforces it,
 *     rather than a denylist we have to keep ahead of. Omitting
 *     `allow-same-origin` additionally gives the frame an opaque origin, so it
 *     cannot reach app cookies or storage even if that changed.
 *
 * `allow-popups allow-popups-to-escape-sandbox` is granted so an authored
 * `<a target="_blank">` still opens. With no scripts in the frame, a popup can
 * only ever come from a real click.
 *
 * The frame is fed via `srcDoc` (never a URL) — that is what makes this block
 * OSS-free: the HTML travels inline in the CourseDefinition. `srcDoc` therefore
 * has no base URL, which is why off-page references can't resolve (the contract
 * warns about that at authoring time, see validate/quality.ts).
 *
 * The document we build wraps the authored fragment in a small base stylesheet
 * so an author who writes bare `<h2>`/`<p>` still gets the course's typography
 * and the student's own accent — the palette is read from the LIVE computed
 * styles of the host at mount, so accent 随人 holds inside the card too.
 */

/** Host CSS custom properties mirrored into the card, with course.css's own fallbacks. */
const MIRRORED_TOKENS: { name: string; fallback: string }[] = [
  { name: "--course-surface", fallback: "#ffffff" },
  { name: "--course-ink", fallback: "#33302e" },
  { name: "--course-secondary", fallback: "#5a5049" },
  { name: "--course-muted", fallback: "#8a827a" },
  { name: "--course-border", fallback: "#efe7dd" },
  { name: "--course-accent", fallback: "#ea5140" },
  { name: "--course-accent-weak", fallback: "#fef0ed" },
  { name: "--course-radius", fallback: "10px" },
];

/**
 * Resolves the mirrored tokens against a live element. Falls back to the
 * literals above outside a browser (SSR, jsdom without layout) so the document
 * is always complete.
 */
function resolveTokens(el: Element | null): string {
  const computed = el && typeof window !== "undefined" && typeof window.getComputedStyle === "function"
    ? window.getComputedStyle(el)
    : null;
  return MIRRORED_TOKENS.map(({ name, fallback }) => {
    const live = computed?.getPropertyValue(name).trim();
    return `${name}: ${live ? live : fallback};`;
  }).join("\n    ");
}

/**
 * The base stylesheet every card starts from. Deliberately modest: it sets the
 * reading defaults an author should not have to restate (font, measure, spacing,
 * table/blockquote/code basics) and nothing opinionated beyond that — every rule
 * here is overridable by the author's own `<style>`, which comes after it.
 */
function baseStyles(tokens: string): string {
  return `
    :root {
    ${tokens}
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      padding: 20px 22px;
      font-family: ui-sans-serif, system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 15px;
      line-height: 1.72;
      color: var(--course-ink);
      background: transparent;
      -webkit-font-smoothing: antialiased;
      overflow-wrap: break-word;
    }
    h1, h2, h3, h4 { line-height: 1.32; margin: 1.4em 0 0.5em; font-weight: 700; }
    h1:first-child, h2:first-child, h3:first-child, h4:first-child { margin-top: 0; }
    h1 { font-size: 1.5em; }
    h2 { font-size: 1.25em; }
    h3 { font-size: 1.08em; }
    p, ul, ol, blockquote, table, pre { margin: 0 0 0.9em; }
    :last-child { margin-bottom: 0; }
    ul, ol { padding-left: 1.4em; }
    li { margin: 0.25em 0; }
    a { color: var(--course-accent); text-underline-offset: 2px; }
    strong { font-weight: 650; }
    blockquote {
      margin-left: 0;
      padding: 2px 0 2px 14px;
      border-left: 3px solid var(--course-accent);
      color: var(--course-secondary);
    }
    code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.92em; }
    code { background: var(--course-accent-weak); padding: 1px 5px; border-radius: 5px; }
    pre { padding: 12px 14px; background: var(--course-accent-weak); border-radius: var(--course-radius); overflow-x: auto; }
    pre code { background: none; padding: 0; }
    table { border-collapse: collapse; width: 100%; font-size: 0.95em; }
    th, td { border: 1px solid var(--course-border); padding: 7px 10px; text-align: left; vertical-align: top; }
    th { background: var(--course-accent-weak); font-weight: 700; }
    img { max-width: 100%; height: auto; }
    hr { border: 0; border-top: 1px solid var(--course-border); margin: 1.2em 0; }
  `;
}

/** Builds the whole srcdoc document: base stylesheet first, authored HTML after. */
export function buildRichTextDocument(html: string, tokens: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${baseStyles(tokens)}</style></head><body>${html}</body></html>`;
}

export const RichTextRenderer: BlockRenderer<RichTextBlock> = ({ block, visible }) => {
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Built ONCE per block: changing `srcDoc` reloads the frame, which would
  // throw away the student's scroll position mid-read on any unrelated
  // re-render (a sibling block revealing, a signed-URL refresh...).
  const doc = useMemo(
    () => buildRichTextDocument(block.html, resolveTokens(rootRef.current ?? document.documentElement)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [block.id, block.html],
  );

  return (
    <div
      ref={rootRef}
      data-block-id={block.id}
      data-block-type="richText"
      hidden={!visible}
      aria-hidden={!visible}
      className="course-block course-block--rich-text"
    >
      <iframe
        className="course-rich-text__frame"
        title={block.title ?? "图文卡片"}
        // No allow-scripts: authored markup is inert BY THE BROWSER, not by a
        // denylist. No allow-same-origin: opaque origin, no app cookies/storage.
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        srcDoc={doc}
      />
    </div>
  );
};
