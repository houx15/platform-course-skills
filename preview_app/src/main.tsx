import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { CourseDefinitionDocument } from "@mind-imprint/course-contract";
import { PreviewCoursePlayer } from "./PreviewCoursePlayer";
import { loadCourseDocument, loadInspectionConfig } from "./previewApi";
import type { InspectionConfig } from "./previewApi";
import { definitionHash } from "./previewAdapters";
import "./styles.css";

function App() {
  const [loaded, setLoaded] = useState<{ document: CourseDefinitionDocument; hash: string; inspection: InspectionConfig | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void Promise.all([loadCourseDocument(), loadInspectionConfig()])
      .then(async ([document, inspection]) => ({ document: document as CourseDefinitionDocument, hash: await definitionHash(document), inspection }))
      .then(setLoaded)
      .catch((caught: Error) => setError(caught.message));
  }, []);
  if (error) return <section className="preview-boot-error"><h1>预览无法启动</h1><p>{error}</p></section>;
  if (!loaded) return <p className="preview-loading">正在加载课程预览…</p>;
  return <PreviewCoursePlayer document={loaded.document} definitionHash={loaded.hash} inspection={loaded.inspection} />;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
