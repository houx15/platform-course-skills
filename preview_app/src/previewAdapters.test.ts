import { describe, expect, it, vi } from "vitest";
import { encodeAssetPath, fallbackScene, SilentPreviewAudioEngine } from "./previewAdapters";

describe("preview adapters", () => {
  it("encodes each asset path segment without changing hierarchy", () => {
    expect(encodeAssetPath("assets/my image/图.png")).toBe("assets/my%20image/%E5%9B%BE.png");
  });

  it("uses authored fallback text without audio or generation", () => {
    expect(fallbackScene("Prepared opening", () => "2026-08-17T00:00:00Z")).toEqual({
      text: "Prepared opening",
      generatedAt: "2026-08-17T00:00:00Z",
      usedSignalTypes: [],
      fallbackUsed: true,
    });
  });

  it("lets narration-gated workflows advance without TTS in preview", async () => {
    const engine = new SilentPreviewAudioEngine();
    const ended = vi.fn();
    engine.onEnded(ended);
    await engine.play();
    await Promise.resolve();
    expect(ended).toHaveBeenCalledOnce();
  });
});
