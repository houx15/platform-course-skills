import { createContext, useContext } from "react";

/**
 * §17.10 — the imperative surface a media renderer exposes so the Slice Workflow
 * can drive it. `playBlock`/`pauseBlock`/`resetBlock` effects (Slice 1 actions)
 * are transient commands, not persisted state, so they reach the media element
 * through this handle rather than through the folded block state.
 */
export interface MediaHandle {
  play(): void;
  pause(): void;
  reset(): void;
}

/**
 * A SlicePlayer-owned registry mapping a block id → its live {@link MediaHandle}.
 * A media renderer registers its handle on mount and unregisters on unmount;
 * SlicePlayer's effect interpreter looks the handle up by target id when it
 * applies a `playBlock`/`pauseBlock`/`resetBlock` effect. Keyed by block id
 * because at most one media renderer owns a given block within a slice.
 */
export class MediaHandleRegistry {
  private readonly handles = new Map<string, MediaHandle>();

  /**
   * Registers `handle` under `blockId`, returning an unregister function. The
   * unregister is identity-guarded: it only evicts the entry if it still points
   * at the handle it registered (a remount that registered a newer handle for
   * the same id is not clobbered by the old cleanup).
   */
  register(blockId: string, handle: MediaHandle): () => void {
    this.handles.set(blockId, handle);
    return () => {
      if (this.handles.get(blockId) === handle) this.handles.delete(blockId);
    };
  }

  get(blockId: string): MediaHandle | undefined {
    return this.handles.get(blockId);
  }
}

const MediaHandleRegistryContext = createContext<MediaHandleRegistry | null>(null);

export const MediaHandleRegistryProvider = MediaHandleRegistryContext.Provider;

/** Reads the SlicePlayer-provided registry; `null` when no media player is mounted. */
export function useMediaHandleRegistry(): MediaHandleRegistry | null {
  return useContext(MediaHandleRegistryContext);
}
