import type { CourseRuntimeEvent } from "@mind-imprint/course-contract";
import type { Clock, IdFactory } from "./adapters";

/** A slice-scoped emitter returned by {@link RuntimeEventBus.bindSlice}. */
export type SliceEmitter = (sourceId: string, type: CourseRuntimeEvent["type"], payload?: unknown) => void;

export type RuntimeEventHandler = (event: CourseRuntimeEvent) => void;

export interface RuntimeEventBusOptions {
  courseId: string;
  sessionId: string;
  idFactory: IdFactory;
  clock: Clock;
  /** Invoked when an event is dropped because its slice is not the active one. */
  onDropped?: (event: CourseRuntimeEvent) => void;
}

/**
 * §17.15 — the typed runtime Event Bus. It normalizes envelopes, binds each
 * event to course/session/part/slice/source ids (stamping id + occurredAt from
 * injected factories), fans out to subscribers, and refuses to deliver an event
 * belonging to a slice other than the active one — this is what "prevents one
 * Slice from consuming another Slice's Events" means.
 *
 * The bus is deterministic: it never reads the wall clock or mints ids itself.
 */
export class RuntimeEventBus {
  private readonly courseId: string;
  private readonly sessionId: string;
  private readonly idFactory: IdFactory;
  private readonly clock: Clock;
  private readonly onDropped?: (event: CourseRuntimeEvent) => void;
  private readonly handlers = new Set<RuntimeEventHandler>();
  private activeSliceId: string | undefined;

  constructor(opts: RuntimeEventBusOptions) {
    this.courseId = opts.courseId;
    this.sessionId = opts.sessionId;
    this.idFactory = opts.idFactory;
    this.clock = opts.clock;
    this.onDropped = opts.onDropped;
  }

  /** Sets which slice's events the bus will deliver. Emitting for any other slice drops. */
  setActiveSlice(sliceId: string): void {
    this.activeSliceId = sliceId;
  }

  get currentSliceId(): string | undefined {
    return this.activeSliceId;
  }

  /** Binds an emitter to a part/slice; calling it stamps and publishes one event. */
  bindSlice(partId: string, sliceId: string): SliceEmitter {
    return (sourceId, type, payload) => {
      const event: CourseRuntimeEvent = {
        id: this.idFactory(),
        sessionId: this.sessionId,
        courseId: this.courseId,
        partId,
        sliceId,
        sourceId,
        type,
        occurredAt: this.clock(),
        payload: payload ?? null,
      };
      this.publish(event);
    };
  }

  subscribe(handler: RuntimeEventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  private publish(event: CourseRuntimeEvent): void {
    if (event.sliceId !== this.activeSliceId) {
      this.onDropped?.(event);
      return;
    }
    for (const handler of this.handlers) handler(event);
  }
}
