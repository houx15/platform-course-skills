import type { RuntimeSceneResult, VideoInteractionDocument } from "@mind-imprint/course-contract";
import {
  InMemorySessionAdapter,
  type Clock,
  type CourseRuntimeAdapters,
  type IdFactory,
  type RuntimeSceneGenerator,
} from "@mind-imprint/course-runtime";
import type { AudioEngine } from "@mind-imprint/course-renderer";

export function encodeAssetPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function fallbackScene(text: string, clock: Clock): RuntimeSceneResult {
  return { text, generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true };
}

export function fallbackGenerator(clock: Clock): RuntimeSceneGenerator {
  return { generate: async (input) => fallbackScene(input.fallback.text, clock) };
}

export function createPreviewAdapters(idFactory: IdFactory, clock: Clock): CourseRuntimeAdapters {
  return {
    assetResolver: { resolve: (path) => `/course-assets/${encodeAssetPath(path)}` },
    sessionAdapter: new InMemorySessionAdapter({ idFactory, clock }),
    openingGenerator: fallbackGenerator(clock),
    closingGenerator: fallbackGenerator(clock),
  };
}

export async function loadVideoInteraction(source: string): Promise<VideoInteractionDocument> {
  const response = await fetch(`/course-assets/${encodeAssetPath(source)}`);
  if (!response.ok) throw new Error(`Unable to load video interaction: ${response.status}`);
  return (await response.json()) as VideoInteractionDocument;
}

export class SilentPreviewAudioEngine implements AudioEngine {
  private listeners = new Set<() => void>();
  async play(): Promise<void> {
    queueMicrotask(() => this.listeners.forEach((listener) => listener()));
  }
  pause(): void {}
  stop(): void {}
  onEnded(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, child]) => [key, sortValue(child)]),
    );
  }
  return value;
}

export async function definitionHash(document: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(sortValue(document)));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
