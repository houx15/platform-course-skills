export type ValidationLayer = "structural" | "referential" | "workflow";

export interface ValidationIssue {
  path: string;
  message: string;
  layer: ValidationLayer;
}
