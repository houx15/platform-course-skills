import { useEffect, useMemo, useState } from "react";
import type { CourseDefinitionDocument, CourseRuntimeEvent } from "@mind-imprint/course-contract";
import { CoursePlayer, InteractionLoaderProvider, AudioEngineProvider } from "@mind-imprint/course-renderer";
import type { CourseProgress } from "@mind-imprint/course-renderer";
import type { RuntimeEventBus } from "@mind-imprint/course-runtime";
import { AnnotationPanel } from "./AnnotationPanel";
import { createPreviewAdapters, loadVideoInteraction, SilentPreviewAudioEngine } from "./previewAdapters";

export function PreviewCoursePlayer({ document, definitionHash }: { document: CourseDefinitionDocument; definitionHash: string }) {
  const [progress, setProgress] = useState<CourseProgress>({ phase: "loading", sliceIndex: 0, sliceCount: 0 });
  const [events, setEvents] = useState<Array<{ id: string; type: string; sourceId: string; sliceId: string | null }>>([]);
  const [visitedSliceIds, setVisitedSliceIds] = useState<string[]>([]);
  const [runtimeErrors, setRuntimeErrors] = useState<string[]>([]);
  const idFactory = useMemo(() => () => crypto.randomUUID(), []);
  const clock = useMemo(() => () => new Date().toISOString(), []);
  const adapters = useMemo(() => createPreviewAdapters(idFactory, clock), [idFactory, clock]);
  const audio = useMemo(() => new SilentPreviewAudioEngine(), []);
  const entries = useMemo(() => document.course.parts.flatMap((part) => part.slices), [document]);

  useEffect(() => {
    if (progress.phase !== "playing") return;
    const sliceId = entries[progress.sliceIndex]?.id;
    if (sliceId) setVisitedSliceIds((current) => current.includes(sliceId) ? current : [...current, sliceId]);
  }, [entries, progress.phase, progress.sliceIndex]);

  useEffect(() => {
    const onError = (event: ErrorEvent) => setRuntimeErrors((current) => [...current, event.message || "Browser runtime error"]);
    const onRejection = (event: PromiseRejectionEvent) => setRuntimeErrors((current) => [...current, String(event.reason ?? "Unhandled promise rejection")]);
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  const observe = (bus: RuntimeEventBus) => {
    bus.subscribe((event: CourseRuntimeEvent) => {
      setEvents((current) => [...current.slice(-99), {
        id: event.id,
        type: event.type,
        sourceId: event.sourceId,
        sliceId: event.sliceId ?? null,
      }]);
    });
  };

  return (
    <main className="preview-shell">
      <section className="preview-stage" aria-label="学生端课程预览">
        <InteractionLoaderProvider value={loadVideoInteraction}>
          <AudioEngineProvider value={audio}>
            <CoursePlayer
              document={document}
              definitionHash={definitionHash}
              adapters={adapters}
              studentId="local-preview-student"
              idFactory={idFactory}
              clock={clock}
              onBusReady={observe}
              onProgress={setProgress}
            />
          </AudioEngineProvider>
        </InteractionLoaderProvider>
      </section>
      <AnnotationPanel document={document} definitionHash={definitionHash} sliceIndex={progress.sliceIndex} events={events} visitedSliceIds={visitedSliceIds} runtimeErrors={runtimeErrors} />
    </main>
  );
}
