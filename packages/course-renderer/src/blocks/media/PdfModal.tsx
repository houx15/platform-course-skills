import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export interface PdfModalProps {
  /** The iframe src (already-resolved signed URL + `#page=` fragment). */
  src: string;
  title: string;
  /** Close the modal — bound to Escape, the backdrop, and the ✕ button. */
  onClose: () => void;
}

/**
 * "Read in a popup" overlay for a course PDF whose inline slot is too small.
 * Portaled to `document.body` (outside `.course-shell`, so its root carries the
 * `.course-pdf-modal` token setup — see styles/course.css). The document opens
 * in a large near-fullscreen panel using the browser's own PDF viewer (same
 * `<iframe>` as inline). Escape, the ✕, and a backdrop click close it; focus
 * moves to the close button on open and is restored to the trigger on unmount.
 */
export function PdfModal({ src, title, onClose }: PdfModalProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    return () => {
      previouslyFocused.current?.focus();
    };
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div className="course-pdf-modal" role="dialog" aria-modal="true" aria-label={title || "PDF"}>
      <div className="course-pdf-modal__backdrop" aria-hidden="true" onClick={onClose} />
      <div className="course-pdf-modal__panel">
        <div className="course-pdf-modal__header">
          <span className="course-pdf-modal__title">{title}</span>
          <button ref={closeRef} type="button" className="course-pdf-modal__close" aria-label="关闭" onClick={onClose}>
            ✕
          </button>
        </div>
        <iframe className="course-pdf-modal__frame" title={title} src={src} />
      </div>
    </div>,
    document.body,
  );
}
