import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { RuntimeSceneResult } from "@mind-imprint/course-contract";
import type { AssetResolver } from "@mind-imprint/course-runtime";
import { OpeningScene } from "../../src/scenes/OpeningScene";
import { AudioEngineProvider } from "../../src/narration/audioEngine";
import { FakeAudioEngine } from "../support/fakeAudioEngine";

const assetResolver: AssetResolver = { resolve: (p) => `/resolved/${p}` };

function baseScene(overrides: Partial<RuntimeSceneResult> = {}): RuntimeSceneResult {
  return {
    text: "欢迎来到这门课程。",
    generatedAt: "2026-08-16T00:00:00.000Z",
    usedSignalTypes: [],
    fallbackUsed: false,
    ...overrides,
  };
}

function renderOpening(
  engine: FakeAudioEngine,
  props: Partial<ComponentProps<typeof OpeningScene>> = {},
) {
  return render(
    <AudioEngineProvider value={engine}>
      <OpeningScene
        scene={baseScene()}
        title="课程标题"
        estimatedMinutes={5}
        objectives={[]}
        learningPreview={[]}
        assetResolver={assetResolver}
        onStart={() => {}}
        {...props}
      />
    </AudioEngineProvider>,
  );
}

describe("OpeningScene", () => {
  it("renders objectives alongside the learning preview (P2-05)", () => {
    renderOpening(new FakeAudioEngine(), {
      objectives: ["理解核心概念", "能够独立完成练习"],
      learningPreview: ["先看一个案例"],
    });

    expect(screen.getByText("理解核心概念")).toBeInTheDocument();
    expect(screen.getByText("能够独立完成练习")).toBeInTheDocument();
    expect(screen.getByText("先看一个案例")).toBeInTheDocument();
  });

  it("does not render an objectives list when there are none", () => {
    renderOpening(new FakeAudioEngine(), { objectives: [] });
    expect(screen.queryByLabelText("学习目标")).toBeNull();
  });

  it("plays scene.audioUrl through the injected engine on mount, resolving a relative key via the assetResolver (P2-04)", () => {
    const engine = new FakeAudioEngine();
    renderOpening(engine, { scene: baseScene({ audioUrl: "audio/opening.mp3" }) });

    expect(engine.calls).toEqual([{ op: "play", url: "/resolved/audio/opening.mp3" }]);
  });

  it("does not re-resolve an already-absolute audioUrl", () => {
    const engine = new FakeAudioEngine();
    renderOpening(engine, { scene: baseScene({ audioUrl: "https://cdn.example.com/opening.mp3" }) });

    expect(engine.calls).toEqual([{ op: "play", url: "https://cdn.example.com/opening.mp3" }]);
  });

  it("never attempts to play when the scene has no audioUrl", () => {
    const engine = new FakeAudioEngine();
    renderOpening(engine);

    expect(engine.calls).toEqual([]);
    expect(screen.queryByRole("button", { name: "播放" })).toBeNull();
  });

  it("shows a one-click 播放 fallback when play() rejects, and never blocks the start action (P2-04)", async () => {
    const engine = new FakeAudioEngine();
    engine.rejectNextPlay = new Error("autoplay blocked");
    const onStart = vi.fn();

    renderOpening(engine, { scene: baseScene({ audioUrl: "audio/opening.mp3" }), onStart });

    // The start action works immediately — a blocked audio play never gates
    // the phase (a workflow waiting on audio must never hang).
    await userEvent.click(screen.getByRole("button", { name: "一起开始吧" }));
    expect(onStart).toHaveBeenCalledTimes(1);

    const fallback = await screen.findByRole("button", { name: "播放" });
    await userEvent.click(fallback);
    expect(engine.calls.filter((c) => c.op === "play")).toHaveLength(2);
  });
});
