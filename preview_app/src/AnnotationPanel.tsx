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
  selectedTargetKey?: string | null;
}

export function AnnotationPanel({ document, definitionHash, sliceIndex, events, visitedSliceIds, runtimeErrors, selectedTargetKey }: AnnotationPanelProps) {
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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");

  useEffect(() => {
    void loadAnnotations().then(setStore).catch((error: Error) => setMessage(error.message));
  }, []);
  useEffect(() => setTargetKey("slice"), [entry?.slice.id]);
  useEffect(() => {
    if (selectedTargetKey) setTargetKey(selectedTargetKey);
  }, [selectedTargetKey]);

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

  const targetLabel = options.find((option) => option.key === targetKey)?.label ?? "当前 Slice";

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

  const persist = async (next: AnnotationDocument, successMessage: string) => {
    try {
      await saveAnnotations(next);
      setStore(next);
      setMessage(successMessage);
    } catch (error) {
      setMessage(`批注保存失败：${(error as Error).message}`);
    }
  };

  const startEdit = (annotation: PreviewAnnotation) => {
    setEditingId(annotation.id);
    setEditingText(annotation.text);
  };

  const saveEdit = async (annotation: PreviewAnnotation) => {
    if (!editingText.trim()) return;
    const updated: PreviewAnnotation = {
      ...annotation,
      status: "open",
      text: editingText.trim(),
      updatedAt: new Date().toISOString(),
      classification: null,
      proposedChange: null,
      resolutionDecisionId: null,
      appliedBlueprintHash: null,
      verifiedAgainstDefinitionHash: null,
      orphanReason: null,
    };
    await persist(
      { ...store, annotations: store.annotations.map((item) => item.id === annotation.id ? updated : item) },
      "批注已修改，并重新进入待处理状态。",
    );
    setEditingId(null);
    setEditingText("");
  };

  const toggleComplete = async (annotation: PreviewAnnotation) => {
    const reopening = annotation.status === "dismissed";
    const updated: PreviewAnnotation = {
      ...annotation,
      status: reopening ? "open" : "dismissed",
      updatedAt: new Date().toISOString(),
      classification: reopening ? null : annotation.classification,
      proposedChange: reopening ? null : annotation.proposedChange,
      resolutionDecisionId: reopening ? null : `decision-complete-${annotation.id}`,
      appliedBlueprintHash: reopening ? null : annotation.appliedBlueprintHash,
      verifiedAgainstDefinitionHash: reopening ? null : annotation.verifiedAgainstDefinitionHash,
      orphanReason: reopening ? null : annotation.orphanReason,
    };
    await persist(
      { ...store, annotations: store.annotations.map((item) => item.id === annotation.id ? updated : item) },
      reopening ? "批注已重新打开。" : "批注已标记完成。",
    );
  };

  const deleteAnnotation = async (annotation: PreviewAnnotation) => {
    if (!window.confirm("确定删除这条批注吗？删除后无法在预览中恢复。")) return;
    await persist(
      { ...store, annotations: store.annotations.filter((item) => item.id !== annotation.id) },
      "批注已删除。",
    );
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
      const pendingCount = store.annotations.filter((annotation) => !["verified", "dismissed"].includes(annotation.status)).length;
      setMessage(pendingCount === 0
        ? "本轮预览已完成，目前没有待处理批注。现在可以让 AI 发布到学生端；尚未选择课程时，AI 会先请你选择课程名称。"
        : `本轮预览已完成，还有 ${pendingCount} 条批注待处理；修改后可以继续预览。`);
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
        <div className="annotation-target" aria-live="polite">
          <span>当前批注目标</span>
          <strong>{targetLabel}</strong>
          <button type="button" onClick={() => setTargetKey("slice")}>批注整页</button>
        </div>
        <label>类型<select value={type} onChange={(event) => setType(event.target.value as PreviewAnnotation["type"])}>{["content", "layout", "workflow", "media", "bug", "question"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="required-check"><input type="checkbox" checked={required} onChange={(event) => setRequired(event.target.checked)} />必须修改</label>
        <label>具体批注<textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="说明哪里需要调整，以及希望学生看到或经历什么。" /></label>
        <button type="button" onClick={() => void addAnnotation()} disabled={!entry || !text.trim()}>保存批注</button>
        {message ? <p className="panel-message">{message}</p> : null}
      </section>
      <section>
        <h2>当前批注</h2>
        <ol className="annotation-list">{store.annotations.map((annotation) => <li key={annotation.id} data-status={annotation.status}>
          <div className="annotation-list__meta"><span>{annotation.type}</span><em>{annotation.status === "dismissed" ? "已完成" : "待处理"}</em></div>
          {editingId === annotation.id ? (
            <div className="annotation-list__editor">
              <label>修改批注内容<textarea value={editingText} onChange={(event) => setEditingText(event.target.value)} /></label>
              <div className="annotation-list__actions">
                <button type="button" onClick={() => void saveEdit(annotation)} disabled={!editingText.trim()}>保存修改</button>
                <button type="button" onClick={() => { setEditingId(null); setEditingText(""); }}>取消</button>
              </div>
            </div>
          ) : <p>{annotation.text}</p>}
          <small>{annotation.target.itemId ?? annotation.target.blockId ?? annotation.target.workflowStepId ?? annotation.target.sliceId}</small>
          {editingId !== annotation.id ? <div className="annotation-list__actions">
            <button type="button" aria-label="修改批注" onClick={() => startEdit(annotation)}>修改</button>
            <button type="button" onClick={() => void toggleComplete(annotation)}>{annotation.status === "dismissed" ? "重新打开" : "标记已完成"}</button>
            <button type="button" className="danger" aria-label="删除批注" onClick={() => void deleteAnnotation(annotation)}>删除</button>
          </div> : null}
        </li>)}</ol>
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
