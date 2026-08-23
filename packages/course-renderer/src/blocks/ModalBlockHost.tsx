import { useEffect, useRef, useState, type ReactNode } from "react";
import type { BlockDefinition, BlockSessionState } from "@mind-imprint/course-contract";
import { InteractionModal } from "./media/InteractionModal";

export interface ModalBlockHostProps {
  block: BlockDefinition;
  state: BlockSessionState;
  /** The block's own renderer element, rendered inside the dialog. */
  children: ReactNode;
}

/** Assessment blocks are the ones the student is being ASKED to act on right now. */
export function isAssessmentBlock(block: BlockDefinition): boolean {
  return block.type === "fillBlank" || block.type === "singleChoice";
}

/**
 * The launcher's label. An explicit `modalLabel` always wins; otherwise it is
 * derived from whatever the block already calls itself, so authoring one is
 * only needed when the button should read differently from the content.
 */
export function modalLabelOf(block: BlockDefinition): string {
  if ("modalLabel" in block && block.modalLabel) return block.modalLabel;
  switch (block.type) {
    case "fillBlank":
    case "singleChoice":
      return block.prompt;
    case "pdf":
      return block.title;
    case "richText":
      return block.title || "参考资料";
    case "images": {
      const first = block.items[0];
      return first?.caption || first?.alt || "图片";
    }
    case "video":
      return "视频";
    case "interactiveHtml":
      return "互动";
    default:
      return "查看";
  }
}

/** The verb on the right-hand side of the launcher, by kind and state. */
function cta(block: BlockDefinition, completed: boolean): string {
  if (isAssessmentBlock(block)) return completed ? "已完成 · 再看一次" : "回答这道题";
  switch (block.type) {
    case "pdf":
      return "打开原文";
    case "video":
      return "播放视频";
    case "images":
      return "查看大图";
    default:
      return "展开查看";
  }
}

/**
 * §9.8 — hosts a block authored `openAs: "modal"`: a compact launcher button in
 * the slot, the block itself in a dialog over the slice.
 *
 * A slice is one desktop screen. Put two or three resources on it and a `grid`
 * gives each a quarter — a PDF page or a slide-sized figure at that size is
 * unreadable. Behind a button each opens at full size on demand and the slot
 * spends its height on what the slice is actually about.
 *
 * Two behaviours, by kind:
 *
 *   - An ASSESSMENT block opens by itself the first time the Workflow enables
 *     it (the student is meant to answer now) and closes itself on completion,
 *     handing the screen back. Reopening after completion REMOUNTS the
 *     renderer, which is why SlicePlayer passes `enabled: false` to a completed
 *     modal assessment — a remounted question would otherwise have lost its
 *     local `locked` flag and could emit a second `block.completed`, driving
 *     the Workflow somewhere the author never authored. The trade is that the
 *     reopened dialog shows the question rather than the feedback; the launcher
 *     carries the 已完成 state instead.
 *   - Every OTHER block (a source, a figure, a video, a reference card) opens
 *     only on press and stays interactive when reopened — replaying a video or
 *     re-reading a PDF is not a hazard, and auto-opening a reference the moment
 *     a slice loads would be obnoxious.
 */
export function ModalBlockHost({ block, state, children }: ModalBlockHostProps) {
  const [open, setOpen] = useState(false);
  const autoOpened = useRef(false);
  const label = modalLabelOf(block);
  const isAssessment = isAssessmentBlock(block);
  const { visible, enabled, completed } = state;

  // Only a question opens on its own, and only once.
  useEffect(() => {
    if (!isAssessment) return;
    if (visible && enabled && !completed && !autoOpened.current) {
      autoOpened.current = true;
      setOpen(true);
    }
  }, [isAssessment, visible, enabled, completed]);

  // Completing a question hands the slide back to whatever it sat on.
  useEffect(() => {
    if (isAssessment && completed) setOpen(false);
  }, [isAssessment, completed]);

  // A hidden block has no launcher and no dialog (§10 — the slot still exists).
  if (!visible) {
    return <div data-block-id={block.id} data-modal-host hidden aria-hidden="true" className="course-block" />;
  }

  return (
    <div
      data-block-id={block.id}
      data-modal-host
      data-modal-kind={isAssessment ? "assessment" : "resource"}
      className="course-block course-block--modal-host"
    >
      <button
        type="button"
        className="course-modal-host__launcher"
        data-modal-launcher
        data-completed={completed ? "true" : "false"}
        disabled={!enabled && !completed}
        onClick={() => setOpen(true)}
      >
        <span className="course-modal-host__prompt">{label}</span>
        <span className="course-modal-host__cta">{cta(block, completed)}</span>
      </button>
      {open ? (
        <InteractionModal ariaLabel={label} onSkip={() => setOpen(false)} dismissLabel="关闭">
          {children}
        </InteractionModal>
      ) : null}
    </div>
  );
}
