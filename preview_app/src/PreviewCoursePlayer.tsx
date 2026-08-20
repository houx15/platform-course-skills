import { useEffect, useMemo, useRef, useState } from "react";
import type { CourseDefinitionDocument, CourseRuntimeEvent } from "@mind-imprint/course-contract";
import { CoursePlayer, InteractionLoaderProvider, AudioEngineProvider } from "@mind-imprint/course-renderer";
import type { CourseProgress } from "@mind-imprint/course-renderer";
import type { RuntimeEventBus } from "@mind-imprint/course-runtime";
import { AnnotationPanel } from "./AnnotationPanel";
import { createPreviewAdapters, loadVideoInteraction, SilentPreviewAudioEngine } from "./previewAdapters";

export function PreviewCoursePlayer({ document, definitionHash }: { document: CourseDefinitionDocument; definitionHash: string }) {
  const [annotationsOpen, setAnnotationsOpen] = useState(false);
  const [annotationMode, setAnnotationMode] = useState(false);
  const [selectedTargetKey, setSelectedTargetKey] = useState<string | null>(null);
  const [progress, setProgress] = useState<CourseProgress>({ phase: "loading", sliceIndex: 0, sliceCount: 0 });
  const [events, setEvents] = useState<Array<{ id: string; type: string; sourceId: string; sliceId: string | null }>>([]);
  const [visitedSliceIds, setVisitedSliceIds] = useState<string[]>([]);
  const [runtimeErrors, setRuntimeErrors] = useState<string[]>([]);
  const idFactory = useMemo(() => () => crypto.randomUUID(), []);
  const clock = useMemo(() => () => new Date().toISOString(), []);
  const adapters = useMemo(() => createPreviewAdapters(idFactory, clock), [idFactory, clock]);
  const audio = useMemo(() => new SilentPreviewAudioEngine(), []);
  const entries = useMemo(() => document.course.parts.flatMap((part) => part.slices), [document]);
  const stageRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (progress.phase !== "playing") return;
    const sliceId = entries[progress.sliceIndex]?.id;
    if (sliceId) setVisitedSliceIds((current) => current.includes(sliceId) ? current : [...current, sliceId]);
  }, [entries, progress.phase, progress.sliceIndex]);

  useEffect(() => {
    setSelectedTargetKey(null);
  }, [progress.sliceIndex]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.querySelectorAll("[data-annotation-selected]").forEach((element) => element.removeAttribute("data-annotation-selected"));
    if (!annotationMode || !selectedTargetKey) return;
    if (selectedTargetKey.startsWith("item:")) {
      const [, blockId, itemId] = selectedTargetKey.split(":");
      const match = [...stage.querySelectorAll<HTMLElement>("[data-item-id]")].find((element) =>
        element.dataset.itemId === itemId && Boolean(element.closest(`[data-block-id="${blockId}"]`)),
      );
      match?.setAttribute("data-annotation-selected", "true");
      return;
    }
    if (selectedTargetKey.startsWith("block:")) {
      const blockId = selectedTargetKey.slice(6);
      const match = [...stage.querySelectorAll<HTMLElement>("[data-block-id], [data-focus-block]")].find((element) =>
        element.dataset.blockId === blockId || element.dataset.focusBlock === blockId,
      );
      match?.setAttribute("data-annotation-selected", "true");
    }
  }, [annotationMode, selectedTargetKey]);

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

  const selectAnnotationTarget = (event: React.MouseEvent<HTMLElement>) => {
    if (!annotationMode) return;
    const element = event.target instanceof Element ? event.target : null;
    if (!element) return;
    const item = element.closest<HTMLElement>("[data-item-id]");
    const block = element.closest<HTMLElement>("[data-block-id]") ?? element.closest<HTMLElement>("[data-focus-block]");
    const blockId = block?.dataset.blockId ?? block?.dataset.focusBlock;
    if (!blockId) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedTargetKey(item?.dataset.itemId ? `item:${blockId}:${item.dataset.itemId}` : `block:${blockId}`);
  };

  return (
    <main className="preview-shell">
      <section ref={stageRef} className={`preview-stage${annotationMode ? " preview-stage--annotation-mode" : ""}`} aria-label="学生端课程预览" onClickCapture={selectAnnotationTarget}>
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
      <div
        className={`annotation-sidebar ${annotationsOpen ? "annotation-sidebar--expanded" : "annotation-sidebar--collapsed"}`}
        style={{ width: annotationsOpen ? 330 : 46 }}
      >
        <button
          type="button"
          className="annotation-toggle"
          aria-controls="course-annotation-drawer"
          aria-expanded={annotationsOpen}
          onClick={() => setAnnotationsOpen((open) => {
            if (open) setAnnotationMode(false);
            return !open;
          })}
        >
          {annotationsOpen ? "关闭课程批注" : "打开课程批注"}
        </button>
        {annotationsOpen ? (
          <div id="course-annotation-drawer" className="annotation-drawer">
            <button
              type="button"
              className="annotation-mode-switch"
              aria-pressed={annotationMode}
              onClick={() => setAnnotationMode((enabled) => !enabled)}
            >
              {annotationMode ? "关闭点选批注" : "开启点选批注"}
            </button>
            <AnnotationPanel document={document} definitionHash={definitionHash} sliceIndex={progress.sliceIndex} events={events} visitedSliceIds={visitedSliceIds} runtimeErrors={runtimeErrors} selectedTargetKey={selectedTargetKey} />
          </div>
        ) : <span className="annotation-rail-label" aria-hidden="true">课程批注</span>}
      </div>
    </main>
  );
}
