export type ValidationLayer = "structural" | "referential" | "workflow" | "quality";

export interface ValidationIssue {
  path: string;
  message: string;
  layer: ValidationLayer;
  /**
   * P2-09 — "error" (the default when omitted) blocks `validateCourseDefinition`'s
   * `ok`; "warn" is a non-blocking authoring-quality nudge (a distinct layer/
   * severity, per the review, not a hard reject) that never fails an otherwise
   * playable course. Only the `quality` layer ever uses "warn" today.
   */
  severity?: "error" | "warn";
}
