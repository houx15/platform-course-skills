import { useEffect, useMemo, useState } from "react";
import type { CourseDefinitionDocument } from "@mind-imprint/course-contract";
import {
  loadAnnotations,
  postPreviewEvidence,
  saveAnnotations,
  type AnnotationDocument,
  type AnnotationTarget,
  type PreviewAnnotation,
} from "./previewApi";

interface AnnotationPanelProps {
  document: CourseDefinitionDocument;
  definitionHash: string;
  sliceIndex: number;
  events: Array<{ id: string; type: string; sourceId: string; sliceId: string | null }>;
  visitedSliceIds: string[];
  runtimeErrors: string[];
}

export function AnnotationPanel({ document, definitionHash, sliceIndex, events, visitedSliceIds, runtimeErrors }: AnnotationPanelProps) {
  const entries = useMemo(
    () => document.course.parts.flatMap((part) => part.slices.map((slice) => ({ part, slice }))),
    [document],
  );
  const entry = entries[Math.max(0, Math.min(sliceIndex, entries.length - 1))];
  const [store, setStore] = useState<AnnotationDocument>({ schemaVersion: "1.0", annotations: [] });
  const [text, setText] = useState("");
  const [type, setType] = useState<PreviewAnnotation["type"]>("content");
  const [required, setRequired] = useState(true);
  const [targetKey, setTargetKey] = useState("slice");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void loadAnnotations().then(setStore).catch((error: Error) => setMessage(error.message));
  }, []);
  useEffect(() => setTargetKey("slice"), [entry?.slice.id]);

  const options = useMemo(() => {
    if (!entry) return [];
    const blockOptions = entry.slice.blocks.flatMap((block) => {
      const options = [{ key: `block:${block.id}`, label: `Block · ${block.id}` }];
      if (block.type === "images") {
        options.push(...block.items.map((item) => ({ key: `item:${block.id}:${item.id}`, label: `Image item · ${item.id}` })));
      }
      return options;
    });
    return [
      { key: "slice", label: `Slice · ${entry.slice.title}` },
      ...blockOptions,
      ...entry.slice.workflow.steps.map((step) => ({ key: `step:${step.id}`, label: `Workflow · ${step.id}` })),
    ];
  }, [entry]);

  const buildTarget = (): AnnotationTarget => {
    if (!entry) throw new Error("No active Slice");
    const target: AnnotationTarget = {
      courseId: document.course.id,
      partId: entry.part.id,
      sliceId: entry.slice.id,
      blockId: null,
      itemId: null,
      workflowStepId: null,
    };
    if (targetKey.startsWith("block:")) target.blockId = targetKey.slice(6);
    if (targetKey.startsWith("item:")) {
      const [, blockId, itemId] = targetKey.split(":");
      target.blockId = blockId ?? null;
      target.itemId = itemId ?? null;
    }
    if (targetKey.startsWith("step:")) target.workflowStepId = targetKey.slice(5);
    return target;
  };

  const addAnnotation = async () => {
    if (!text.trim()) return;
    const now = new Date().toISOString();
    const annotation: PreviewAnnotation = {
      id: `annotation-${crypto.randomUUID()}`,
      type,
      status: "open",
      required,
      target: buildTarget(),
      definitionHash,
      text: text.trim(),
      screenshotPath: null,
      createdAt: now,
      updatedAt: now,
      classification: null,
      proposedChange: null,
      resolutionDecisionId: null,
      appliedBlueprintHash: null,
      verifiedAgainstDefinitionHash: null,
      orphanReason: null,
      reboundFromDefinitionHash: null,
    };
    const next = { ...store, annotations: [...store.annotations, annotation] };
    await saveAnnotations(next);
    setStore(next);
    setText("");
    setMessage("批注已保存，AI 可以按稳定目标继续修改。 ");
  };

  const completeReview = async () => {
    try {
      await postPreviewEvidence({
        viewport: { width: window.innerWidth, height: window.innerHeight },
        visitedSliceIds,
        exercisedEvents: events,
        runtimeErrors,
        teacherConfirmed: true,
        completedAt: new Date().toISOString(),
      });
      setMessage("本轮预览审查已记录，可以继续完成 G7。 ");
    } catch (error) {
      setMessage(`暂时不能完成预览审查：${(error as Error).message}`);
    }
  };

  const totalSlices = entries.length;
  const allVisited = entries.every(({ slice }) => visitedSliceIds.includes(slice.id));

  return (
    <aside className="preview-panel" aria-label="课程批注">
      <header>
        <p className="eyebrow">LOCAL COURSE REVIEW</p>
        <h1>课程预览与批注</h1>
        <p>{entry ? `${entry.part.title} / ${entry.slice.title}` : "Opening / Closing"}</p>
      </header>
      <section className="annotation-form">
        <label>批注目标<select value={targetKey} onChange={(event) => setTargetKey(event.target.value)}>{options.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
        <label>类型<select value={type} onChange={(event) => setType(event.target.value as PreviewAnnotation["type"])}>{["content", "layout", "workflow", "media", "bug", "question"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="required-check"><input type="checkbox" checked={required} onChange={(event) => setRequired(event.target.checked)} />必须修改</label>
        <label>具体批注<textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="说明哪里需要调整，以及希望学生看到或经历什么。" /></label>
        <button type="button" onClick={() => void addAnnotation()} disabled={!entry || !text.trim()}>保存批注</button>
        {message ? <p className="panel-message">{message}</p> : null}
      </section>
      <section>
        <h2>当前批注</h2>
        <ol className="annotation-list">{store.annotations.map((annotation) => <li key={annotation.id}><span>{annotation.type}</span><p>{annotation.text}</p><small>{annotation.target.blockId ?? annotation.target.workflowStepId ?? annotation.target.sliceId}</small></li>)}</ol>
      </section>
      <section className="review-completion">
        <h2>完成本轮审查</h2>
        <p>已查看 {visitedSliceIds.length} / {totalSlices} 个 Slice。页面打开本身不会通过审查。</p>
        <button type="button" onClick={() => void completeReview()} disabled={!allVisited}>确认我已完整审查</button>
      </section>
      <details>
        <summary>Runtime diagnostics</summary>
        {runtimeErrors.map((error) => <p className="runtime-error" key={error}>{error}</p>)}
        <ol className="event-list">{events.slice(-20).map((event, index) => <li key={`${event.type}-${index}`}>{event.type} · {event.sourceId}</li>)}</ol>
      </details>
    </aside>
  );
}
