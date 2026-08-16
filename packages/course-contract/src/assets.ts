import type { CourseDefinitionDocument } from "./course";

// collectAssetPaths walks a CourseDefinition and returns the deduped set of
// relative asset paths it references — every field typed relativeAssetPathSchema
// in the contract (keep in sync with that schema's usages). Absolute
// (http(s)://) and inline (data:) references are excluded: they need no signing.
function isRelativeAsset(p: string | undefined): p is string {
  return !!p && !/^https?:\/\//i.test(p) && !p.startsWith("data:");
}

export function collectAssetPaths(document: CourseDefinitionDocument): string[] {
  const out = new Set<string>();
  const add = (p: string | undefined) => {
    if (isRelativeAsset(p)) out.add(p);
  };
  const { course } = document;

  add(course.opening.fallback.audio);
  add(course.closing.fallback.audio);

  for (const part of course.parts) {
    for (const slice of part.slices) {
      for (const n of slice.narrations) add(n.audio);
      for (const block of slice.blocks) {
        switch (block.type) {
          case "images":
            for (const item of block.items) add(item.source);
            break;
          case "pdf":
            add(block.source);
            break;
          case "video":
            add(block.source);
            add(block.poster);
            add(block.captions);
            add(block.interaction?.source);
            break;
          case "interactiveHtml":
            add(block.source);
            break;
          // text, fillBlank, singleChoice carry no assets
        }
      }
    }
  }
  return [...out];
}
