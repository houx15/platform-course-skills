import { CourseDefinitionDocument, type CourseDefinition } from "../course";
import { validateReferential } from "./referential";
import { validateSliceWorkflow } from "./workflow";
import type { ValidationIssue } from "./types";

export type ValidateResult =
  | { ok: true; course: CourseDefinition }
  | { ok: false; issues: ValidationIssue[] };

/**
 * The single validation entry point. Runs structural (Zod) validation first;
 * if the shape is wrong it returns those issues and stops (referential and
 * workflow layers assume a well-formed shape). Otherwise it runs referential
 * validation plus every slice's workflow-graph validation and returns the
 * combined list (ok only when it is empty).
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
  const issues: ValidationIssue[] = [...validateReferential(course)];
  course.parts.forEach((part, pi) =>
    part.slices.forEach((slice, si) => issues.push(...validateSliceWorkflow(slice, `parts[${pi}].slices[${si}]`))),
  );
  return issues.length === 0 ? { ok: true, course } : { ok: false, issues };
}

export * from "./types";
