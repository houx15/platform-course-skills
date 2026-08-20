import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface ImageLightboxProps {
  /** Already-resolved image URL (the renderer resolves paths, never this component). */
  src: string;
  alt: string;
  /** Optional caption shown under the enlarged image. */
  caption?: string;
  /** Close the lightbox — bound to Escape, the backdrop, and the close button. */
  onClose: () => void;
}

const MIN_SCALE = 1;
const MAX_SCALE = 6;
const WHEEL_ZOOM_SENSITIVITY = 0.0018; // scale change per wheel delta unit

function clampScale(s: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
}

/**
 * Click-to-enlarge overlay for a course figure. Portaled to `document.body`
 * (outside `.course-shell`, so its root carries the `.course-lightbox` token
 * setup — see styles/course.css). The enlarged image can be **zoomed with the
 * scroll wheel** and **dragged to pan** once zoomed. Escape, the ✕ button, and
 * a click on the backdrop all close it; a drag that ends over the backdrop does
 * NOT close it (the image captures the pointer). Focus moves to the close
 * button on open and is restored to the trigger on unmount.
 */
export function ImageLightbox({ src, alt, caption, onClose }: ImageLightboxProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const figureRef = useRef<HTMLElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  // Where the drag started, in screen coords, plus the offset at that moment.
  const dragStart = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null);

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

  // Wheel-to-zoom. Attached natively as a NON-passive listener so we can
  // preventDefault the page/background scroll (React's synthetic onWheel is
  // passive on the root and cannot). Zooming back to 1× recenters the pan.
  useEffect(() => {
    const el = figureRef.current;
    if (!el) return;
    function onWheel(e: WheelEvent) {
      e.preventDefault();
      setScale((prev) => {
        const next = clampScale(prev * Math.exp(-e.deltaY * WHEEL_ZOOM_SENSITIVITY));
        if (next <= MIN_SCALE) setOffset({ x: 0, y: 0 });
        return next;
      });
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
      dragStart.current = { px: e.clientX, py: e.clientY, ox: offset.x, oy: offset.y };
      setDragging(true);
    },
    [offset.x, offset.y],
  );

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const start = dragStart.current;
    if (!start) return;
    setOffset({ x: start.ox + (e.clientX - start.px), y: start.oy + (e.clientY - start.py) });
  }, []);

  const endDrag = useCallback((e: React.PointerEvent) => {
    if (!dragStart.current) return;
    (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    dragStart.current = null;
    setDragging(false);
  }, []);

  if (typeof document === "undefined") return null;

  const zoomed = scale > MIN_SCALE;

  return createPortal(
    <div className="course-lightbox" role="dialog" aria-modal="true" aria-label={alt || caption || "放大图片"}>
      <div className="course-lightbox__backdrop" aria-hidden="true" onClick={onClose} />
      <button ref={closeRef} type="button" className="course-lightbox__close" aria-label="关闭" onClick={onClose}>
        ✕
      </button>
      <figure ref={figureRef} className="course-lightbox__figure">
        <img
          className="course-lightbox__img"
          src={src}
          alt={alt}
          draggable={false}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            cursor: dragging ? "grabbing" : zoomed ? "grab" : "zoom-in",
          }}
        />
        {caption ? <figcaption className="course-lightbox__caption">{caption}</figcaption> : null}
      </figure>
      <p className="course-lightbox__hint" aria-hidden="true">
        滚轮缩放 · 拖拽移动 · Esc 关闭
      </p>
    </div>,
    document.body,
  );
}
