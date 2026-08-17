import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { RuntimeSceneResult } from "@mind-imprint/course-contract";
import type { AssetResolver } from "@mind-imprint/course-runtime";
import { ClosingScene } from "../../src/scenes/ClosingScene";
import { AudioEngineProvider } from "../../src/narration/audioEngine";
import { FakeAudioEngine } from "../support/fakeAudioEngine";

const assetResolver: AssetResolver = { resolve: (p) => `/resolved/${p}` };

function baseScene(overrides: Partial<RuntimeSceneResult> = {}): RuntimeSceneResult {
  return {
    text: "这门课程到此结束。",
    generatedAt: "2026-08-16T00:00:00.000Z",
    usedSignalTypes: [],
    fallbackUsed: false,
    ...overrides,
  };
}

function renderClosing(engine: FakeAudioEngine, props: Partial<ComponentProps<typeof ClosingScene>> = {}) {
  return render(
    <AudioEngineProvider value={engine}>
      <ClosingScene
        scene={baseScene()}
        summary="小结文字"
        takeaways={["要点一"]}
        transferApplications={["迁移应用一"]}
        assetResolver={assetResolver}
        onComplete={() => {}}
        {...props}
      />
    </AudioEngineProvider>,
  );
}

describe("ClosingScene", () => {
  it("renders the 完成课程 control and fires onComplete only when it is clicked", async () => {
    const onComplete = vi.fn();
    renderClosing(new FakeAudioEngine(), { onComplete });

    expect(onComplete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "完成课程" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("plays scene.audioUrl through the injected engine on mount, resolving a relative key via the assetResolver (P2-04)", () => {
    const engine = new FakeAudioEngine();
    renderClosing(engine, { scene: baseScene({ audioUrl: "audio/closing.mp3" }) });

    expect(engine.calls).toEqual([{ op: "play", url: "/resolved/audio/closing.mp3" }]);
  });

  it("never attempts to play when the scene has no audioUrl", () => {
    const engine = new FakeAudioEngine();
    renderClosing(engine);

    expect(engine.calls).toEqual([]);
    expect(screen.queryByRole("button", { name: "播放" })).toBeNull();
  });

  it("shows a one-click 播放 fallback when play() rejects, and never blocks 完成课程 (P2-04)", async () => {
    const engine = new FakeAudioEngine();
    engine.rejectNextPlay = new Error("autoplay blocked");
    const onComplete = vi.fn();

    renderClosing(engine, { scene: baseScene({ audioUrl: "audio/closing.mp3" }), onComplete });

    // 完成课程 works immediately — a blocked audio play never gates the phase.
    await userEvent.click(screen.getByRole("button", { name: "完成课程" }));
    expect(onComplete).toHaveBeenCalledTimes(1);

    const fallback = await screen.findByRole("button", { name: "播放" });
    await userEvent.click(fallback);
    expect(engine.calls.filter((c) => c.op === "play")).toHaveLength(2);
  });
});
