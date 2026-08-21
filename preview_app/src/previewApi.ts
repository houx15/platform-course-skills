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

export interface InspectionConfig {
  inspection: true;
  nonce: string;
  definitionHash: string;
  expectedStates: string[];
}

export interface InspectionObservation {
  nonce: string;
  definitionHash: string;
  stateId: string;
  sliceId: string;
  viewport: { width: number; height: number };
  blocks: Array<{
    blockId: string;
    x: number;
    y: number;
    width: number;
    height: number;
    visible: boolean;
    enabled: boolean;
  }>;
  overflow: { horizontal: boolean; vertical: boolean };
  runtimeErrors: string[];
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

export const loadCourseDocument = () => jsonRequest<unknown>("/__course_preview/document");
export async function loadInspectionConfig(): Promise<InspectionConfig | null> {
  const response = await fetch("/__course_preview/inspection/config");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as InspectionConfig;
}
export const postInspectionObservation = (observation: InspectionObservation) =>
  jsonRequest<{ ok: true; stateId: string }>("/__course_preview/inspection/observations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(observation),
  });
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
