import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FillBlankRenderer } from "../../src/blocks/assessment/FillBlankRenderer";
import type { FillBlankBlock } from "../../src/blocks/types";
import type { BlockSessionState } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";

const assetResolver = { resolve: (p: string) => `/resolved/${p}` };

interface Recorded {
  sourceId: string;
  type: string;
  payload: unknown;
}

function renderFill(
  block: FillBlankBlock,
  opts: { emit?: SliceEmitter; enabled?: boolean; state?: Partial<BlockSessionState> } = {},
) {
  const events: Recorded[] = [];
  const emit: SliceEmitter = opts.emit ?? ((sourceId, type, payload) => events.push({ sourceId, type: String(type), payload }));
  const state: BlockSessionState = { visible: true, enabled: true, completed: false, attempts: 0, ...opts.state };
  const utils = render(
    <FillBlankRenderer
      block={block}
      assetResolver={assetResolver}
      state={state}
      visible
      enabled={opts.enabled ?? true}
      emit={emit}
    />,
  );
  return { ...utils, events };
}

const gradedBlock = (maxAttempts: number): FillBlankBlock => ({
  id: "fb1",
  type: "fillBlank",
  prompt: "输入第 2 页的标题。",
  placeholder: "章节标题",
  assessment: {
    mode: "graded",
    acceptedAnswers: ["Evidence Check"],
    caseSensitive: false,
    correctFeedback: "你找到了正确的章节。",
    incorrectFeedback: "回到第 2 页再看看标题。",
  },
  completion: { rule: "submit-correct-or-exhausted", maxAttempts },
});

const reflectionBlock: FillBlankBlock = {
  id: "fb-reflect",
  type: "fillBlank",
  prompt: "在比较两个论断之前你会核实什么？",
  assessment: { mode: "reflection", rubric: "至少写出一项具体核实。" },
  completion: { rule: "submit-any" },
};

const typeNames = (events: Recorded[]) => events.map((e) => e.type);

describe("FillBlankRenderer", () => {
  it("renders prompt, a labelled input with placeholder, and a submit button", () => {
    renderFill(gradedBlock(2));
    const input = screen.getByLabelText("输入第 2 页的标题。") as HTMLInputElement;
    expect(input).toHaveAttribute("placeholder", "章节标题");
    expect(screen.getByRole("button", { name: "提交" })).toBeInTheDocument();
  });

  it("graded submit-correct-or-exhausted: wrong then wrong-final → incorrect, then attemptsExhausted + completed + lock", async () => {
    const user = userEvent.setup();
    const { events } = renderFill(gradedBlock(2));
    const input = () => screen.getByLabelText("输入第 2 页的标题。") as HTMLInputElement;

    // attempt 1: wrong → submitted then incorrect, no completion, input stays enabled
    await user.type(input(), "Wrong Heading");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.incorrect"]);
    expect(events[0]).toMatchObject({ sourceId: "fb1", payload: { value: "Wrong Heading" } });
    expect(events[1]).toMatchObject({ payload: { value: "Wrong Heading", attempt: 1 } });
    expect(screen.getByText("回到第 2 页再看看标题。")).toBeInTheDocument();
    expect(input()).not.toBeDisabled();

    // attempt 2 (final): wrong → attemptsExhausted then block.completed, input locks
    await user.clear(input());
    await user.type(input(), "Still Wrong");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual([
      "answer.submitted",
      "answer.incorrect",
      "answer.submitted",
      "answer.attemptsExhausted",
      "block.completed",
    ]);
    expect(events[3]).toMatchObject({ payload: { value: "Still Wrong", attempt: 2 } });
    expect(input()).toBeDisabled();
    expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
  });

  it("graded correct on attempt 1 → submitted, correct, block.completed; shows correctFeedback; locks", async () => {
    const user = userEvent.setup();
    const { events } = renderFill(gradedBlock(3));
    await user.type(screen.getByLabelText("输入第 2 页的标题。"), "Evidence Check");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.correct", "block.completed"]);
    expect(events[1]).toMatchObject({ payload: { value: "Evidence Check", attempt: 1 } });
    expect(screen.getByText("你找到了正确的章节。")).toBeInTheDocument();
    expect(screen.getByLabelText("输入第 2 页的标题。")).toBeDisabled();
  });

  it("matches case-insensitively by default (trims too)", async () => {
    const user = userEvent.setup();
    const { events } = renderFill(gradedBlock(3));
    await user.type(screen.getByLabelText("输入第 2 页的标题。"), "  evidence check  ");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.correct", "block.completed"]);
  });

  it("case-sensitive rejects a case mismatch", async () => {
    const user = userEvent.setup();
    const block = gradedBlock(3);
    block.assessment = { ...block.assessment, caseSensitive: true } as FillBlankBlock["assessment"];
    const { events } = renderFill(block);
    await user.type(screen.getByLabelText("输入第 2 页的标题。"), "evidence check");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.incorrect"]);
  });

  it("reflection: any submission → answer.submitted + block.completed, no correctness events", async () => {
    const user = userEvent.setup();
    const { events } = renderFill(reflectionBlock);
    await user.type(screen.getByLabelText("在比较两个论断之前你会核实什么？"), "我会核实样本范围。");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual(["answer.submitted", "block.completed"]);
    expect(events[0]).toMatchObject({ payload: { value: "我会核实样本范围。" } });
    expect(screen.getByLabelText("在比较两个论断之前你会核实什么？")).toBeDisabled();
  });

  it("enabled=false disables input + button and emits nothing on click", async () => {
    const user = userEvent.setup();
    const { events } = renderFill(gradedBlock(2), { enabled: false });
    const button = screen.getByRole("button", { name: "提交" });
    expect(button).toBeDisabled();
    expect(screen.getByLabelText("输入第 2 页的标题。")).toBeDisabled();
    await user.click(button);
    expect(events).toHaveLength(0);
  });

  it("seeds its attempt counter from state.attempts (continuity across re-enable)", async () => {
    const user = userEvent.setup();
    // one prior attempt already recorded → this submission is attempt 2 (final) of 2
    const { events } = renderFill(gradedBlock(2), { state: { attempts: 1 } });
    await user.type(screen.getByLabelText("输入第 2 页的标题。"), "Nope");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.attemptsExhausted", "block.completed"]);
    expect(events[1]).toMatchObject({ payload: { attempt: 2 } });
  });
});
