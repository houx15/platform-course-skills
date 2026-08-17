import { createContext, useContext, useEffect, useRef } from "react";
import type { ReactNode } from "react";
import type { TargetRef } from "@mind-imprint/course-contract";

/**
 * §17 focus actions — the current focus target for the active slice, or `null`
 * when nothing is focused. SlicePlayer sets this from `focus` / `clearFocus`
 * effects; block/item wrappers read it and highlight themselves when they match.
 */
const FocusContext = createContext<TargetRef | null>(null);

export const FocusProvider = FocusContext.Provider;

export function useCurrentFocus(): TargetRef | null {
  return useContext(FocusContext);
}

/** True when a block-LEVEL focus (no `itemId`) targets `blockId`. */
export function isBlockFocused(focus: TargetRef | null, blockId: string): boolean {
  return focus !== null && focus.blockId === blockId && !("itemId" in focus);
}

/**
 * The item id focused inside `blockId`, or `undefined`. Used by SlicePlayer to
 * derive a block renderer's `focusedItemId` prop from the current focus.
 */
export function focusedItemIdFor(focus: TargetRef | null, blockId: string): string | undefined {
  if (focus !== null && focus.blockId === blockId && "itemId" in focus) return focus.itemId;
  return undefined;
}

export interface FocusTargetProps {
  blockId: string;
  /** When given, this wrapper represents an item inside the block, not the block. */
  itemId?: string;
  className?: string;
  /**
   * §Slice5 / P2-06 — a meaningful accessible name for this wrapper, derived
   * by the caller from the block's own authored content/title (e.g. a
   * question's `prompt`, a PDF's `title`) — NEVER a raw internal id. Applied
   * only while this target is the focused one; omitted (not a machine-id
   * fallback) when the caller has nothing meaningful to offer, letting the
   * accessible name fall back to the wrapped content's own text.
   */
  label?: string;
  /**
   * The block's own layout visibility flag (§10). Defaults to `true` for
   * callers that don't track it (e.g. standalone item-level wrappers). A
   * hidden block's wrapper is marked `aria-hidden` — the actual box
   * reservation (no reflow on reveal) is the course stylesheet's job
   * (`.course-block[hidden]` — see `styles/course.css`).
   */
  visible?: boolean;
  children: ReactNode;
}

/** True when the environment asks for no non-essential motion (§P2-06 scroll behavior). */
function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Wraps a block (or an item within it) and, when the current focus matches:
 * sets `data-focused="true"` + the `.course-focus-ring` class (§P2-06 —
 * defined in the course stylesheet, `styles/course.css`, not injected here),
 * moves real DOM (keyboard/assistive-tech) focus onto the wrapper, and
 * scrolls it into view. ONLY the actively-focused wrapper carries
 * `tabIndex={-1}` (a valid programmatic focus target even when the block it
 * wraps has no natively focusable element) and, when the caller supplied a
 * meaningful `label`, an `aria-label` — every other wrapper is plain DOM with
 * no programmatic focusability and no announced name (§Slice5 review nit:
 * Slice 4 previously put `tabIndex={-1}` + a machine-id `aria-label` on
 * EVERY block wrapper). Losing focus (the match no longer holds — e.g. a
 * `clearFocus` effect) blurs the wrapper if it still holds DOM focus, so
 * emphasis doesn't linger past its target.
 */
export function FocusTarget({ blockId, itemId, className, label, visible = true, children }: FocusTargetProps) {
  const focus = useCurrentFocus();
  const focused =
    itemId === undefined
      ? isBlockFocused(focus, blockId)
      : focus !== null && focus.blockId === blockId && "itemId" in focus && focus.itemId === itemId;

  const ref = useRef<HTMLDivElement | null>(null);

  // `tabIndex` is managed IMPERATIVELY (not a declarative JSX prop) so the
  // ordering is exact: on losing focus, `blur()` is called WHILE the element
  // is still `tabindex="-1"` (a focus target with no other native
  // focusability must still carry it to be blur-able at all), and only THEN
  // is the attribute removed — so a non-focused wrapper is left with no
  // programmatic focusability at all, never a dangling `tabindex="-1"`.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (focused) {
      el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
      el.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    } else {
      if (document.activeElement === el) el.blur();
      el.removeAttribute("tabindex");
    }
  }, [focused]);

  return (
    <div
      ref={ref}
      data-focus-block={blockId}
      data-focus-item={itemId}
      data-focused={focused ? "true" : undefined}
      aria-hidden={visible ? undefined : "true"}
      aria-label={focused && label ? label : undefined}
      className={[className, focused ? "course-focus-ring" : null].filter(Boolean).join(" ") || undefined}
    >
      {children}
    </div>
  );
}
