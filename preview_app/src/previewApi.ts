export interface AnnotationTarget {
  courseId: string;
  partId: string | null;
  sliceId: string | null;
  blockId: string | null;
  itemId: string | null;
  workflowStepId: string | null;
}

export interface PreviewAnnotation {
  id: string;
  type: "content" | "layout" | "workflow" | "media" | "bug" | "question";
  status: "open" | "proposed" | "accepted" | "applied" | "verified" | "dismissed" | "orphaned";
  required: boolean;
  target: AnnotationTarget;
  definitionHash: string;
  text: string;
  screenshotPath: string | null;
  createdAt: string;
  updatedAt: string;
  classification: "mechanical" | "semantic" | "runtime-bug" | null;
  proposedChange: string | null;
  resolutionDecisionId: string | null;
  appliedBlueprintHash: string | null;
  verifiedAgainstDefinitionHash: string | null;
  orphanReason: string | null;
  reboundFromDefinitionHash: string | null;
}

export interface AnnotationDocument {
  schemaVersion: "1.0";
  annotations: PreviewAnnotation[];
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

export const loadCourseDocument = () => jsonRequest<unknown>("/__course_preview/document");
export const loadAnnotations = () => jsonRequest<AnnotationDocument>("/__course_preview/annotations");
export const saveAnnotations = (document: AnnotationDocument) =>
  jsonRequest<{ ok: true }>("/__course_preview/annotations", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(document),
  });

export async function postPreviewEvidence(evidence: Record<string, unknown>): Promise<void> {
  await jsonRequest("/__course_preview/evidence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(evidence),
  });
}
