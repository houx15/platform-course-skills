import type { CourseDefinition } from "../course";
import type { ValidationIssue } from "./types";

/**
 * Referential validation (§5, §8, §9.6/§9.7, §10, §14/§19.2). Operates on an
 * already structurally-valid CourseDefinition (post-Zod). Deterministic: same
 * input → same ordered issue list.
 */
export function validateReferential(course: CourseDefinition): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const add = (path: string, message: string) => issues.push({ path, message, layer: "referential" });

  // --- id uniqueness helper ---
  const seen = <T>(items: T[], key: (t: T) => string, kind: string, path: (i: number) => string) => {
    const counts = new Map<string, number>();
    items.forEach((it) => counts.set(key(it), (counts.get(key(it)) ?? 0) + 1));
    items.forEach((it, i) => {
      if ((counts.get(key(it)) ?? 0) > 1) add(path(i), `duplicate ${kind} id '${key(it)}'`);
    });
  };

  const allBlocks: { block: any; path: string }[] = [];
  const objectiveIds = new Set(course.objectives.map((o) => o.id));

  seen(course.objectives, (o) => o.id, "objective", (i) => `objectives[${i}]`);
  seen(course.parts, (p) => p.id, "part", (i) => `parts[${i}]`);

  const sliceEntries: { slice: any; path: string }[] = [];
  course.parts.forEach((part, pi) => {
    part.objectiveIds.forEach((oid, oi) => {
      if (!objectiveIds.has(oid)) add(`parts[${pi}].objectiveIds[${oi}]`, `unknown objective '${oid}'`);
    });
    part.slices.forEach((slice, si) => sliceEntries.push({ slice, path: `parts[${pi}].slices[${si}]` }));
  });
  seen(sliceEntries.map((e) => e.slice), (s) => s.id, "slice", (i) => sliceEntries[i]!.path);

  // --- per-slice checks ---
  sliceEntries.forEach(({ slice, path }) => {
    const blockIds = new Set<string>();
    slice.blocks.forEach((b: any, bi: number) => {
      if (blockIds.has(b.id)) add(`${path}.blocks[${bi}]`, `duplicate block id '${b.id}' within slice`);
      blockIds.add(b.id);
      allBlocks.push({ block: b, path: `${path}.blocks[${bi}]` });
    });
    slice.objectiveIds.forEach((oid: string, oi: number) => {
      if (!objectiveIds.has(oid)) add(`${path}.objectiveIds[${oi}]`, `unknown objective '${oid}'`);
    });

    // narration id uniqueness within slice
    seen(slice.narrations, (n: any) => n.id, "narration", (i) => `${path}.narrations[${i}]`);

    // layout slot ↔ block assignment: each block in exactly one slot, each slot id real
    const assignment = new Map<string, number>();
    slice.layout.slots.forEach((slot: any, sli: number) => {
      slot.blockIds.forEach((bid: string) => {
        if (!blockIds.has(bid)) add(`${path}.layout.slots[${sli}]`, `slot references unknown block '${bid}'`);
        assignment.set(bid, (assignment.get(bid) ?? 0) + 1);
      });
    });
    slice.blocks.forEach((b: any, bi: number) => {
      const n = assignment.get(b.id) ?? 0;
      if (n === 0) add(`${path}.blocks[${bi}]`, `block '${b.id}' is not assigned to a slot`);
      if (n > 1) add(`${path}.blocks[${bi}]`, `block '${b.id}' is assigned to more than one slot`);
    });

    // assessment cross-field rules (§9.6, §9.7, §14)
    slice.blocks.forEach((b: any, bi: number) => {
      if (b.type === "singleChoice" && b.assessment.mode === "graded") {
        const opts = new Set(b.options.map((o: any) => o.id));
        if (!opts.has(b.assessment.correctOptionId)) {
          add(`${path}.blocks[${bi}]`, `correctOptionId '${b.assessment.correctOptionId}' is not an option`);
        }
      }
      if (b.type === "fillBlank" && b.assessment.mode === "graded" && b.completion.rule === "submit-any") {
        add(`${path}.blocks[${bi}]`, `graded fill-blank is incompatible with completion 'submit-any'`);
      }
      if (b.type === "video" && b.completion?.rule === "video-ended-and-interactions-completed" && !b.interaction) {
        add(`${path}.blocks[${bi}]`, `video completion requires an interaction reference`);
      }
    });
  });

  // global block id uniqueness across the whole CourseDefinition (§8)
  seen(allBlocks, (e) => e.block.id, "block", (i) => allBlocks[i]!.path);

  // objective evidence references (global block set)
  const globalBlockIds = new Set(allBlocks.map((e) => e.block.id));
  course.objectives.forEach((o, oi) => {
    o.evidenceBlockIds.forEach((bid, ei) => {
      if (!globalBlockIds.has(bid)) add(`objectives[${oi}].evidenceBlockIds[${ei}]`, `evidence block '${bid}' does not exist`);
    });
  });

  return issues;
}
