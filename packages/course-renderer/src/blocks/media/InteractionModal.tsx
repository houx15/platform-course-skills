import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Elements the focus trap treats as tab stops inside the dialog panel. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface InteractionModalProps {
  /** Accessible name for the dialog — the cue's authored prompt. */
  ariaLabel: string;
  /**
   * Present ONLY for a skippable (optional, `required:false`) cue. Renders an
   * explicit "跳过" control and makes Escape resume without completing. A
   * required cue omits this — there is no dismissal path until it completes.
   */
  onSkip?: () => void;
  children: ReactNode;
}

/**
 * §14 / P1-02 — the accessible cue dialog: portaled to `document.body`, a
 * dimmed backdrop (visual only — no click-to-dismiss, so a stray click can
 * never silently discard a required interaction), `role="dialog"` +
 * `aria-modal="true"`, a focus trap that cycles Tab/Shift+Tab within the
 * panel, and focus restoration to whatever had focus before the cue opened.
 */
export function InteractionModal({ ariaLabel, onSkip, children }: InteractionModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // Capture the pre-open focus target once, move focus into the dialog, and
  // restore it on close/unmount.
  useEffect(() => {
    previouslyFocused.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelRef.current?.focus();
    return () => {
      previouslyFocused.current?.focus();
    };
  }, []);

  // Focus trap + Escape-to-skip (skippable cues only), attached to `document`
  // since the panel is portaled outside the renderer's own DOM subtree.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onSkip?.();
        return;
      }
      if (e.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      // Length was just checked above, so these are always defined.
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      const active = document.activeElement;
      const outside = !(active instanceof Node) || !panel.contains(active);
      if (e.shiftKey) {
        if (outside || active === first) {
          e.preventDefault();
          last.focus();
        }
      } else if (outside || active === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onSkip]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div className="course-video__cue-overlay">
      <div className="course-video__cue-backdrop" aria-hidden="true" />
      <div ref={panelRef} role="dialog" aria-modal="true" aria-label={ariaLabel} tabIndex={-1} className="course-video__cue-modal">
        {children}
        {onSkip ? (
          <button type="button" className="course-video__cue-skip" onClick={onSkip}>
            跳过
          </button>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
