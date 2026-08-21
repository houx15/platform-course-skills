import type { CourseDefinitionDocument } from "../course";
import { collectAssetPaths } from "../assets";
import type { ValidationIssue } from "./types";

// The server's per-course signing cap (apps/api/internal/api/course_asset_urls.go)
// — a course that references more assets than this can never have all of them
// signed, so it isn't actually playable end-to-end even though every other
// layer would accept it.
const MAX_ASSETS = 256;

// A block "produces evidence" when a student's own action on it — an answer,
// an attempt, an interaction result — lands in BlockSessionState. text /
// images / pdf are read-only display: an objective's evidenceBlockIds
// pointing at one is almost certainly an authoring mistake (nothing to
// observe/grade), but not a structural break, hence WARN not HARD.
const EVIDENCE_PRODUCING_BLOCK_TYPES = new Set(["singleChoice", "fillBlank", "video", "interactiveHtml"]);

// estimatedMinutes vs. the authored per-slice estimatedSeconds total: flag
// when they diverge by more than this fraction of the declared minutes. Not a
// contract-breaking mismatch (both are independently authored numbers), so WARN.
const MINUTES_MISMATCH_TOLERANCE = 0.35;

// An off-page reference inside a richText card's HTML: `src="http…"`,
// `href="http…"`, or a CSS `url(http…)`. Google Fonts included — the card is
// isolated, nothing outside it loads.
const EXTERNAL_REF = /(?:\b(?:src|href)\s*=\s*["']?\s*https?:)|(?:url\(\s*["']?\s*https?:)/i;

/**
 * Contract-quality checks (P2-09). Deterministic authoring invariants that go
 * beyond pure referential integrity (validateReferential): each check is
 * either a genuine playability break (HARD — `severity: "error"`, the
 * default, blocks `ok` in validate/index.ts) or a strong authoring smell
 * worth surfacing without rejecting an otherwise-playable course (WARN —
 * `severity: "warn"`, never blocks `ok`). Operates on the whole document
 * (not just `course`) because the asset-cap check needs collectAssetPaths's
 * document-shaped input; same post-Zod precondition as validateReferential.
 */
export function validateQuality(document: CourseDefinitionDocument): ValidationIssue[] {
  const { course } = document;
  const issues: ValidationIssue[] = [];
  const add = (path: string, message: string, severity: "error" | "warn" = "error") =>
    issues.push({ path, message, layer: "quality", severity });

  // --- HARD: the server's 256-asset signing cap.
  const assetCount = collectAssetPaths(document).length;
  if (assetCount > MAX_ASSETS) {
    add("", `course references ${assetCount} assets, exceeding the server's ${MAX_ASSETS}-asset cap`);
  }

  let totalEstimatedSeconds = 0;
  const blockTypeById = new Map<string, string>();

  course.parts.forEach((part, pi) => {
    part.slices.forEach((slice, si) => {
      const slicePath = `parts[${pi}].slices[${si}]`;
      totalEstimatedSeconds += slice.estimatedSeconds;

      slice.blocks.forEach((block: any, bi: number) => {
        blockTypeById.set(block.id, block.type);
        const blockPath = `${slicePath}.blocks[${bi}]`;

        // --- WARN: empty text content renders nothing.
        if (block.type === "text" && block.content.trim().length === 0) {
          add(blockPath, `text block '${block.id}' has empty content — it will render nothing`, "warn");
        }

        // --- WARN: a richText card is rendered from `srcdoc`, which has NO
        // base URL and sits behind the app's CSP — so an off-page reference
        // (a remote image, a webfont, a background-image URL) simply doesn't
        // load, leaving a hole the author cannot see when previewing the raw
        // HTML in a browser. Not a playability break (the text still reads),
        // hence WARN, but it is the single most likely richText surprise.
        if (block.type === "richText" && EXTERNAL_REF.test(block.html)) {
          add(
            blockPath,
            `richText block '${block.id}' references an off-page URL — a card is rendered from srcdoc (no base URL, CSP-restricted), so it will not load. Inline it as a data: URI, or use an images/video/pdf block.`,
            "warn",
          );
        }

        // --- HARD: image item id uniqueness + presentation:"single" arity
        // (the renderer only ever shows the first item for "single" — a
        // multi-item "single" block silently discards the rest).
        if (block.type === "images") {
          const counts = new Map<string, number>();
          block.items.forEach((item: any) => counts.set(item.id, (counts.get(item.id) ?? 0) + 1));
          block.items.forEach((item: any, ii: number) => {
            if ((counts.get(item.id) ?? 0) > 1) {
              add(`${blockPath}.items[${ii}]`, `duplicate image item id '${item.id}' within block '${block.id}'`);
            }
          });
          if (block.presentation === "single" && block.items.length !== 1) {
            add(
              blockPath,
              `images block '${block.id}' has presentation:"single" but ${block.items.length} items — the renderer only shows the first, discarding the rest`,
            );
          }
        }

        // --- HARD: singleChoice option id uniqueness (ambiguous answer ids).
        if (block.type === "singleChoice") {
          const counts = new Map<string, number>();
          block.options.forEach((opt: any) => counts.set(opt.id, (counts.get(opt.id) ?? 0) + 1));
          block.options.forEach((opt: any, oi: number) => {
            if ((counts.get(opt.id) ?? 0) > 1) {
              add(`${blockPath}.options[${oi}]`, `duplicate option id '${opt.id}' within block '${block.id}'`);
            }
          });
        }
      });
    });
  });

  // --- WARN: declared estimatedMinutes vs. the authored per-slice total.
  const estimatedSecondsFromMinutes = course.estimatedMinutes * 60;
  if (estimatedSecondsFromMinutes > 0) {
    const relativeDiff = Math.abs(estimatedSecondsFromMinutes - totalEstimatedSeconds) / estimatedSecondsFromMinutes;
    if (relativeDiff > MINUTES_MISMATCH_TOLERANCE) {
      add(
        "estimatedMinutes",
        `estimatedMinutes (${course.estimatedMinutes}) implies ${estimatedSecondsFromMinutes}s, but the slices total ${totalEstimatedSeconds}s`,
        "warn",
      );
    }
  }

  // --- WARN: objective evidence should point at blocks that actually
  // produce evidence, not static display.
  course.objectives.forEach((objective, oi) => {
    objective.evidenceBlockIds.forEach((blockId, ei) => {
      const type = blockTypeById.get(blockId);
      // Unknown ids are validateReferential's job (evidence block '...' does
      // not exist) — only flag ids that DO resolve, to a non-evidence type.
      if (type && !EVIDENCE_PRODUCING_BLOCK_TYPES.has(type)) {
        add(
          `objectives[${oi}].evidenceBlockIds[${ei}]`,
          `evidence block '${blockId}' is a '${type}' block, which produces no learner evidence`,
          "warn",
        );
      }
    });
  });

  return issues;
}
