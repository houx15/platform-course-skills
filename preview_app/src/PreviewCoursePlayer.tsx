import { useMemo, useState } from "react";
import type { CourseDefinitionDocument, CourseRuntimeEvent } from "@mind-imprint/course-contract";
import { CoursePlayer, InteractionLoaderProvider, AudioEngineProvider } from "@mind-imprint/course-renderer";
import type { CourseProgress } from "@mind-imprint/course-renderer";
import type { RuntimeEventBus } from "@mind-imprint/course-runtime";
import { AnnotationPanel } from "./AnnotationPanel";
import { createPreviewAdapters, loadVideoInteraction, SilentPreviewAudioEngine } from "./previewAdapters";

export function PreviewCoursePlayer({ document, definitionHash }: { document: CourseDefinitionDocument; definitionHash: string }) {
  const [progress, setProgress] = useState<CourseProgress>({ phase: "loading", sliceIndex: 0, sliceCount: 0 });
  const [events, setEvents] = useState<Array<{ type: string; sourceId: string }>>([]);
  const [runtimeErrors] = useState<string[]>([]);
  const idFactory = useMemo(() => () => crypto.randomUUID(), []);
  const clock = useMemo(() => () => new Date().toISOString(), []);
  const adapters = useMemo(() => createPreviewAdapters(idFactory, clock), [idFactory, clock]);
  const audio = useMemo(() => new SilentPreviewAudioEngine(), []);

  const observe = (bus: RuntimeEventBus) => {
    bus.subscribe((event: CourseRuntimeEvent) => {
      setEvents((current) => [...current.slice(-99), { type: event.type, sourceId: event.sourceId }]);
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
      <AnnotationPanel document={document} definitionHash={definitionHash} sliceIndex={progress.sliceIndex} events={events} runtimeErrors={runtimeErrors} />
    </main>
  );
}
