import { CourseDefinitionDocument, type CourseDefinition } from "../course";
import { validateReferential } from "./referential";
import { validateSliceWorkflow } from "./workflow";
import { validateQuality } from "./quality";
import type { ValidationIssue } from "./types";

export type ValidateResult =
  | { ok: true; course: CourseDefinition; warnings: ValidationIssue[] }
  | { ok: false; issues: ValidationIssue[] };

/**
 * The single validation entry point. Runs structural (Zod) validation first;
 * if the shape is wrong it returns those issues and stops (referential,
 * workflow, and quality layers assume a well-formed shape). Otherwise it runs
 * referential validation, the P2-09 quality checks, and every slice's
 * workflow-graph validation. `ok` is false only when at least one issue is
 * blocking (`severity` omitted or "error") — a WARN-only quality issue (a
 * non-blocking authoring nudge) never fails an otherwise-playable course; its
 * warnings still surface on the `ok: true` result for a host that wants them.
 */
export function validateCourseDefinition(input: unknown): ValidateResult {
  const parsed = CourseDefinitionDocument.safeParse(input);
  if (!parsed.success) {
    return {
      ok: false,
      issues: parsed.error.issues.map((i) => ({ path: i.path.join("."), message: i.message, layer: "structural" as const })),
    };
  }
  const course = parsed.data.course;
  const issues: ValidationIssue[] = [...validateReferential(course), ...validateQuality(parsed.data)];
  course.parts.forEach((part, pi) =>
    part.slices.forEach((slice, si) => issues.push(...validateSliceWorkflow(slice, `parts[${pi}].slices[${si}]`))),
  );
  const hasBlocking = issues.some((i) => i.severity !== "warn");
  if (hasBlocking) return { ok: false, issues };
  return { ok: true, course, warnings: issues.filter((i) => i.severity === "warn") };
}

export * from "./types";
