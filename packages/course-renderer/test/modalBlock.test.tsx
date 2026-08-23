import { act, fireEvent, render, screen } from "@testing-library/react";
import type { SliceDefinition } from "@mind-imprint/course-contract";
import { RuntimeEventBus, InMemorySessionAdapter, type CourseRuntimeAdapters } from "@mind-imprint/course-runtime";
import { SlicePlayer } from "../src/slice/SlicePlayer";
import { AudioEngineProvider } from "../src/narration/audioEngine";
import { FakeAudioEngine } from "./support/fakeAudioEngine";

const PART_ID = "modal-part";
const clock = () => "2026-08-23T00:00:00.000Z";

function makeIdFactory() {
  let n = 0;
  return () => `ev-${++n}`;
}

function fallbackGenerator() {
  return { generate: async () => ({ text: "", generatedAt: clock(), usedSignalTypes: [], fallbackUsed: true }) };
}

/**
 * A PPT-sized figure that needs the whole slot, with its question authored
 * `openAs: "modal"` so it arrives over the figure instead of shrinking it.
 */
const modalSlice: SliceDefinition = {
  id: "modal-slice",
  title: "看图作答",
  objectiveIds: ["obj-one"],
  estimatedSeconds: 90,
  blocks: [
    {
      id: "figure",
      type: "images",
      presentation: "single",
      items: [{ id: "fig-1", source: "images/slide-14.png", alt: "两组比较" }],
    },
    {
      id: "question",
      type: "singleChoice",
      prompt: "这两组能直接比较吗？",
      options: [
        { id: "yes", label: "能" },
        { id: "not-yet", label: "还不能" },
      ],
      assessment: { mode: "survey" },
      completion: { rule: "submit-any" },
      openAs: "modal",
    },
  ],
  layout: { preset: "full", slots: [{ id: "main", blockIds: ["figure", "question"] }] },
  narrations: [],
  workflow: {
    version: "1.0",
    initialStepId: "ask",
    initialState: { visibleBlockIds: ["figure", "question"], enabledBlockIds: ["figure", "question"] },
    steps: [
      {
        id: "ask",
        enterActions: [{ type: "enable", targetId: "question" }],
        transitions: [{ on: { type: "block.completed", sourceId: "question" }, to: "done" }],
      },
      { id: "done", enterActions: [{ type: "clearFocus" }, { type: "completeSlice" }], transitions: [] },
    ],
  },
  navigation: { revisit: "restore-completed-state", autoNext: false, previous: "allowed", manualNext: "after-completion" },
};

/**
 * The other half of §9.8: several RESOURCES on one screen. Inline, a grid would
 * give each of these a quarter of the slice — a PDF page at that size is
 * unreadable. Behind buttons they open at full size on demand.
 */
const resourceSlice: SliceDefinition = {
  id: "resource-slice",
  title: "三份材料",
  objectiveIds: ["obj-one"],
  estimatedSeconds: 120,
  blocks: [
    { id: "brief", type: "text", content: "对照这几份材料再作判断。" },
    { id: "source-pdf", type: "pdf", title: "Nature 原文", source: "docs/paper.pdf", openAs: "modal" },
    {
      id: "chart",
      type: "images",
      presentation: "single",
      items: [{ id: "c1", source: "images/fig3.png", alt: "Fig. 3" }],
      openAs: "modal",
      modalLabel: "Fig. 3 的图注",
    },
  ],
  layout: { preset: "full", slots: [{ id: "main", blockIds: ["brief", "source-pdf", "chart"] }] },
  narrations: [],
  workflow: {
    version: "1.0",
    initialStepId: "read",
    initialState: {
      visibleBlockIds: ["brief", "source-pdf", "chart"],
      enabledBlockIds: ["brief", "source-pdf", "chart"],
    },
    steps: [{ id: "read", enterActions: [{ type: "completeSlice" }], transitions: [] }],
  },
  navigation: { revisit: "restore-completed-state", autoNext: false, previous: "allowed", manualNext: "after-completion" },
};

async function setup(slice: SliceDefinition) {
  const sessionAdapter = new InMemorySessionAdapter({ idFactory: makeIdFactory(), clock });
  const session = await sessionAdapter.create({ courseId: "modal-course", studentId: "student-1" });
  const adapters: CourseRuntimeAdapters = {
    assetResolver: { resolve: (p) => `/resolved/${p}` },
    sessionAdapter,
    openingGenerator: fallbackGenerator(),
    closingGenerator: fallbackGenerator(),
  };
  const bus = new RuntimeEventBus({ courseId: "modal-course", sessionId: session.id, idFactory: makeIdFactory(), clock });
  const engine = new FakeAudioEngine();
  const onSliceComplete = vi.fn();
  let container!: HTMLElement;
  await act(async () => {
    const r = render(
      <AudioEngineProvider value={engine}>
        <SlicePlayer
          slice={slice}
          partId={PART_ID}
          sessionId={session.id}
          adapters={adapters}
          bus={bus}
          onSliceComplete={onSliceComplete}
          onNavigateNext={vi.fn()}
        />
      </AudioEngineProvider>,
    );
    container = r.container;
  });
  return { container, onSliceComplete };
}

const dialog = () => document.querySelector('[role="dialog"]');
const launcher = (c: HTMLElement) => c.querySelector("[data-modal-launcher]") as HTMLButtonElement;
const launchers = (c: HTMLElement) => [...c.querySelectorAll("[data-modal-launcher]")] as HTMLButtonElement[];

describe("openAs: modal — a question over its figure", () => {
  it("opens over the slice on entry and keeps the figure's slot free", async () => {
    const { container } = await setup(modalSlice);

    // The question is in a dialog, not competing with the figure for slot height.
    expect(dialog()).not.toBeNull();
    expect(dialog()!.textContent).toContain("这两组能直接比较吗？");
    // The figure still renders in the slot.
    expect(container.querySelector('[data-block-id="figure"]')).not.toBeNull();
    // What the slot holds for the question is only the compact launcher.
    const host = container.querySelector('[data-block-id="question"][data-modal-host]');
    expect(host).not.toBeNull();
    expect(host!.querySelector('[data-block-type="singleChoice"]')).toBeNull();
  });

  it("can be dismissed to study the figure and reopened from the launcher", async () => {
    const { container } = await setup(modalSlice);

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(dialog()).toBeNull();

    fireEvent.click(launcher(container));
    expect(dialog()).not.toBeNull();
  });

  it("closes once the question completes, and cannot be answered twice", async () => {
    const { container, onSliceComplete } = await setup(modalSlice);

    fireEvent.click(screen.getByRole("radio", { name: "还不能" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "提交" }));
    });

    expect(onSliceComplete).toHaveBeenCalledTimes(1);
    // The dialog gets out of the way so the figure is unobstructed again.
    expect(dialog()).toBeNull();
    expect(launcher(container)).toHaveAttribute("data-completed", "true");

    // Reopening remounts the renderer; it must come back INERT so a second
    // submission can never drive the workflow past where the author authored.
    fireEvent.click(launcher(container));
    expect(dialog()).not.toBeNull();
    expect(screen.getByRole("radio", { name: "还不能" })).toBeDisabled();
    expect(onSliceComplete).toHaveBeenCalledTimes(1);
  });

  it("leaves an inline question in its slot", async () => {
    // Rebuild the question explicitly rather than mapping over the block union
    // — `images` carries its own unrelated `presentation` (item layout), and a
    // spread across the union would let TS widen one onto the other.
    const [figure, question] = modalSlice.blocks;
    const inline: SliceDefinition = {
      ...modalSlice,
      blocks: [figure!, { ...(question as Extract<typeof question, { type: "singleChoice" }>), openAs: "inline" }],
    };
    const { container } = await setup(inline);
    expect(dialog()).toBeNull();
    expect(container.querySelector('[data-block-type="singleChoice"]')).not.toBeNull();
  });
});

describe("openAs: modal — resources behind a button", () => {
  it("shows one launcher per resource and opens NONE of them on entry", async () => {
    const { container } = await setup(resourceSlice);

    expect(launchers(container)).toHaveLength(2);
    // A reference must not ambush the student the moment the slice loads —
    // only an assessment auto-opens.
    expect(dialog()).toBeNull();
    // Neither resource is taking slot height.
    expect(container.querySelector('[data-block-type="pdf"]')).toBeNull();
    expect(container.querySelector('[data-block-type="images"]')).toBeNull();
    // The inline text block is untouched.
    expect(container.querySelector('[data-block-type="text"]')).not.toBeNull();
  });

  it("labels each button from the block, and lets modalLabel override", async () => {
    const { container } = await setup(resourceSlice);
    const text = launchers(container).map((b) => b.textContent ?? "");
    expect(text[0]).toContain("Nature 原文");
    expect(text[0]).toContain("打开原文");
    expect(text[1]).toContain("Fig. 3 的图注"); // modalLabel wins over the item's alt
    expect(text[1]).toContain("查看大图");
  });

  it("opens the pressed resource, and stays interactive when reopened", async () => {
    const { container } = await setup(resourceSlice);
    const pdfLauncher = launchers(container)[0]!;

    fireEvent.click(pdfLauncher);
    expect(dialog()).not.toBeNull();
    expect(dialog()!.querySelector('[data-block-type="pdf"]')).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(dialog()).toBeNull();

    // A resource is not one-shot: reopening gives back a live block, unlike a
    // completed assessment, which comes back read-only.
    fireEvent.click(pdfLauncher);
    expect(dialog()!.querySelector('[data-block-type="pdf"]')).not.toBeNull();
    expect(container.querySelector('[data-modal-kind="resource"]')).not.toBeNull();
  });
});
