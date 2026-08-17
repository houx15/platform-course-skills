import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SingleChoiceRenderer } from "../../src/blocks/assessment/SingleChoiceRenderer";
import type { SingleChoiceBlock } from "../../src/blocks/types";
import type { BlockSessionState } from "@mind-imprint/course-contract";
import type { SliceEmitter } from "@mind-imprint/course-runtime";

const assetResolver = { resolve: (p: string) => `/resolved/${p}` };

interface Recorded {
  sourceId: string;
  type: string;
  payload: unknown;
}

function renderChoice(
  block: SingleChoiceBlock,
  opts: { emit?: SliceEmitter; enabled?: boolean; state?: Partial<BlockSessionState> } = {},
) {
  const events: Recorded[] = [];
  const emit: SliceEmitter = opts.emit ?? ((sourceId, type, payload) => events.push({ sourceId, type: String(type), payload }));
  const state: BlockSessionState = { visible: true, enabled: true, completed: false, attempts: 0, ...opts.state };
  const utils = render(
    <SingleChoiceRenderer
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

const gradedBlock = (maxAttempts: number): SingleChoiceBlock => ({
  id: "q1",
  type: "singleChoice",
  prompt: "两个结论能直接比较吗？",
  options: [
    { id: "yes", label: "能" },
    { id: "not-yet", label: "还不能" },
  ],
  assessment: {
    mode: "graded",
    correctOptionId: "not-yet",
    correctFeedback: "正确，需要先核实边界与方法。",
    incorrectFeedback: "结论相反并不能证明可直接比较。",
  },
  completion: { rule: "submit-correct-or-exhausted", maxAttempts },
});

const surveyBlock: SingleChoiceBlock = {
  id: "q-survey",
  type: "singleChoice",
  prompt: "你现在更认同哪个论断？",
  options: [
    { id: "a", label: "论断 A" },
    { id: "b", label: "论断 B" },
    { id: "uncertain", label: "还需更多证据" },
  ],
  assessment: { mode: "survey" },
  completion: { rule: "submit-any" },
};

const typeNames = (events: Recorded[]) => events.map((e) => e.type);
const submitBtn = () => screen.getByRole("button", { name: "提交" });

describe("SingleChoiceRenderer", () => {
  it("renders prompt + a radiogroup of labelled options + a submit button", () => {
    renderChoice(gradedBlock(3));
    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "能" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "还不能" })).toBeInTheDocument();
    expect(submitBtn()).toBeInTheDocument();
  });

  it("submit is disabled until an option is selected", async () => {
    const user = userEvent.setup();
    const { events } = renderChoice(gradedBlock(3));
    expect(submitBtn()).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "还不能" }));
    expect(submitBtn()).not.toBeDisabled();
    await user.click(submitBtn());
    expect(events[0]).toMatchObject({ sourceId: "q1", type: "answer.submitted", payload: { value: "not-yet" } });
  });

  it("graded correct → submitted, correct, block.completed; correctFeedback; locks", async () => {
    const user = userEvent.setup();
    const { events } = renderChoice(gradedBlock(3));
    await user.click(screen.getByRole("radio", { name: "还不能" }));
    await user.click(submitBtn());
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.correct", "block.completed"]);
    expect(events[1]).toMatchObject({ payload: { value: "not-yet", attempt: 1 } });
    expect(screen.getByText("正确，需要先核实边界与方法。")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "还不能" })).toBeDisabled();
    expect(submitBtn()).toBeDisabled();
  });

  it("graded maxAttempts:3 wrong twice then correct → incorrect, incorrect, then correct+completed", async () => {
    const user = userEvent.setup();
    const { events } = renderChoice(gradedBlock(3));

    await user.click(screen.getByRole("radio", { name: "能" }));
    await user.click(submitBtn());
    await user.click(screen.getByRole("radio", { name: "能" }));
    await user.click(submitBtn());
    await user.click(screen.getByRole("radio", { name: "还不能" }));
    await user.click(submitBtn());

    expect(typeNames(events)).toEqual([
      "answer.submitted",
      "answer.incorrect",
      "answer.submitted",
      "answer.incorrect",
      "answer.submitted",
      "answer.correct",
      "block.completed",
    ]);
    expect(events[1]).toMatchObject({ payload: { attempt: 1 } });
    expect(events[3]).toMatchObject({ payload: { attempt: 2 } });
    expect(events[5]).toMatchObject({ payload: { attempt: 3 } });
  });

  it("survey → answer.submitted + block.completed only, no correctness events; locks", async () => {
    const user = userEvent.setup();
    const { events } = renderChoice(surveyBlock);
    await user.click(screen.getByRole("radio", { name: "还需更多证据" }));
    await user.click(submitBtn());
    expect(typeNames(events)).toEqual(["answer.submitted", "block.completed"]);
    expect(events[0]).toMatchObject({ payload: { value: "uncertain" } });
    expect(screen.getByRole("radio", { name: "还需更多证据" })).toBeDisabled();
  });

  it("enabled=false disables the radios + button and emits nothing", async () => {
    const user = userEvent.setup();
    const { events } = renderChoice(gradedBlock(2), { enabled: false });
    expect(submitBtn()).toBeDisabled();
    expect(screen.getByRole("radio", { name: "能" })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "还不能" }));
    await user.click(submitBtn());
    expect(events).toHaveLength(0);
  });

  it("seeds its attempt counter from state.attempts (continuity across re-enable)", async () => {
    const user = userEvent.setup();
    // two prior attempts → this wrong submission is attempt 3 (final) of 3 → exhausted
    const { events } = renderChoice(gradedBlock(3), { state: { attempts: 2 } });
    await user.click(screen.getByRole("radio", { name: "能" }));
    await user.click(submitBtn());
    expect(typeNames(events)).toEqual(["answer.submitted", "answer.attemptsExhausted", "block.completed"]);
    expect(events[1]).toMatchObject({ payload: { attempt: 3 } });
  });
});
