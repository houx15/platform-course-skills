import { useEffect, useMemo, useRef, useState } from "react";
import type { CourseDefinitionDocument, CourseRuntimeEvent } from "@mind-imprint/course-contract";
import { CoursePlayer, InteractionLoaderProvider, AudioEngineProvider } from "@mind-imprint/course-renderer";
import type { CourseProgress } from "@mind-imprint/course-renderer";
import type { RuntimeEventBus } from "@mind-imprint/course-runtime";
import { AnnotationPanel } from "./AnnotationPanel";
import { createPreviewAdapters, loadVideoInteraction, SilentPreviewAudioEngine } from "./previewAdapters";
import { postInspectionObservation } from "./previewApi";
import type { InspectionConfig } from "./previewApi";

export function PreviewCoursePlayer({ document, definitionHash, inspection = null }: { document: CourseDefinitionDocument; definitionHash: string; inspection?: InspectionConfig | null }) {
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
  const entryIdentities = useMemo(
    () => document.course.parts.flatMap((part) => part.slices.map((slice) => ({ partId: part.id, sliceId: slice.id }))),
    [document],
  );
  const [inspectionSliceIndex, setInspectionSliceIndex] = useState(0);
  const [inspectionSessionId, setInspectionSessionId] = useState<string | null>(null);
  const stageRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!inspection) return;
    const selectFromHash = () => {
      const match = window.location.hash.match(/^#inspection-slice=(\d+)$/);
      const requested = match ? Number(match[1]) - 1 : 0;
      setInspectionSliceIndex(Math.max(0, Math.min(entries.length - 1, requested)));
    };
    selectFromHash();
    window.addEventListener("hashchange", selectFromHash);
    return () => window.removeEventListener("hashchange", selectFromHash);
  }, [entries.length, inspection]);

  useEffect(() => {
    if (!inspection) return;
    const entry = entries[inspectionSliceIndex];
    const identity = entryIdentities[inspectionSliceIndex];
    if (!entry || !identity) return;
    let cancelled = false;
    setInspectionSessionId(null);
    setProgress({ phase: "loading", sliceIndex: inspectionSliceIndex, sliceCount: entries.length });
    void (async () => {
      const session = await adapters.sessionAdapter.create({ courseId: document.course.id, studentId: "local-inspection" });
      await adapters.sessionAdapter.setStatus(session.id, "in-progress");
      await adapters.sessionAdapter.setCurrent(session.id, {
        partId: identity.partId,
        sliceId: identity.sliceId,
        workflowStepId: entry.workflow.initialStepId,
      });
      await adapters.sessionAdapter.setDefinitionHash(session.id, definitionHash);
      if (!cancelled) setInspectionSessionId(session.id);
    })();
    return () => { cancelled = true; };
  }, [adapters, definitionHash, document.course.id, entries, entryIdentities, inspection, inspectionSliceIndex]);

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

  useEffect(() => {
    if (!inspection || progress.phase !== "playing") return;
    const identity = entryIdentities[progress.sliceIndex];
    const stage = stageRef.current;
    if (!identity || !stage) return;
    const timer = window.setTimeout(() => {
      const blocks = [...stage.querySelectorAll<HTMLElement>("[data-block-id], [data-focus-block]")]
        .map((element) => {
          const blockId = element.dataset.blockId ?? element.dataset.focusBlock;
          if (!blockId) return null;
          const rect = element.getBoundingClientRect();
          const style = window.getComputedStyle(element);
          const visible = style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
          const controls = [...element.querySelectorAll<HTMLElement>("button, input, textarea, select, iframe, video, [role='button']")];
          const enabled = controls.some((control) => !(control as HTMLButtonElement).disabled && control.getAttribute("aria-disabled") !== "true");
          return { blockId, x: rect.x, y: rect.y, width: rect.width, height: rect.height, visible, enabled };
        })
        .filter((item): item is NonNullable<typeof item> => item !== null)
        .filter((item, index, all) => all.findIndex((candidate) => candidate.blockId === item.blockId) === index);
      void postInspectionObservation({
        nonce: inspection.nonce,
        definitionHash: inspection.definitionHash,
        stateId: `${identity.partId}/${identity.sliceId}/default`,
        sliceId: identity.sliceId,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        blocks,
        overflow: { horizontal: stage.scrollWidth > stage.clientWidth, vertical: stage.scrollHeight > stage.clientHeight },
        runtimeErrors,
      }).catch((caught: Error) => {
        setRuntimeErrors((current) => current.includes(caught.message) ? current : [...current, caught.message]);
      });
    }, 100);
    return () => window.clearTimeout(timer);
  }, [definitionHash, entryIdentities, inspection, progress.phase, progress.sliceIndex, runtimeErrors]);

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
    <main className={`preview-shell${inspection ? " preview-shell--inspection" : ""}`}>
      {inspection ? <div className="inspection-toolbar" role="status">
        <button
          type="button"
          disabled={inspectionSliceIndex === 0}
          onClick={() => { window.location.hash = `inspection-slice=${inspectionSliceIndex}`; }}
        >上一页</button>
        <span>检查模式 · {inspectionSliceIndex + 1} / {entries.length}</span>
        <button
          type="button"
          disabled={inspectionSliceIndex >= entries.length - 1}
          onClick={() => { window.location.hash = `inspection-slice=${inspectionSliceIndex + 2}`; }}
        >下一页</button>
      </div> : null}
      <section ref={stageRef} className={`preview-stage${annotationMode ? " preview-stage--annotation-mode" : ""}`} aria-label="学生端课程预览" onClickCapture={selectAnnotationTarget}>
        <InteractionLoaderProvider value={loadVideoInteraction}>
          <AudioEngineProvider value={audio}>
            {!inspection || inspectionSessionId ? <CoursePlayer
              key={inspection ? inspectionSessionId : "teacher-preview"}
              document={document}
              definitionHash={definitionHash}
              adapters={adapters}
              studentId={inspection ? "local-inspection" : "local-preview-student"}
              sessionId={inspectionSessionId ?? undefined}
              idFactory={idFactory}
              clock={clock}
              onBusReady={observe}
              onProgress={setProgress}
            /> : <p className="preview-loading">正在打开检查页面…</p>}
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
