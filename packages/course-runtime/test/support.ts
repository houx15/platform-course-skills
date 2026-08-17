import type { SliceDefinition, SliceWorkflow } from "@mind-imprint/course-contract";

/**
 * The §15 golden Slice workflow ("observe and answer"), constructed inline so
 * the runtime package does not depend on course-contract's test-only fixtures.
 * It exercises linear steps, media completion, a branch (correct / incorrect /
 * attempts-exhausted) with remediation looping back, and a terminal
 * completeSlice + navigate step.
 */
export function sampleWorkflow(): SliceWorkflow {
  return {
    version: "1.0",
    initialStepId: "introduce",
    initialState: { visibleBlockIds: ["case-video"], enabledBlockIds: [] },
    steps: [
      {
        id: "introduce",
        enterActions: [
          { type: "focus", target: { blockId: "case-video" } },
          { type: "playNarration", narrationId: "introduce-video" },
        ],
        transitions: [{ on: { type: "narration.ended", sourceId: "introduce-video" }, to: "watch-video" }],
      },
      {
        id: "watch-video",
        enterActions: [
          { type: "enable", targetId: "case-video" },
          { type: "playBlock", targetId: "case-video" },
        ],
        transitions: [{ on: { type: "block.completed", sourceId: "case-video" }, to: "introduce-question" }],
      },
      {
        id: "introduce-question",
        enterActions: [
          { type: "show", targetId: "comparison-question" },
          { type: "enable", targetId: "comparison-question" },
          { type: "focus", target: { blockId: "comparison-question" } },
          { type: "playNarration", narrationId: "introduce-question" },
        ],
        transitions: [{ on: { type: "narration.ended", sourceId: "introduce-question" }, to: "wait-for-answer" }],
      },
      {
        id: "wait-for-answer",
        enterActions: [{ type: "enable", targetId: "comparison-question" }],
        transitions: [
          { on: { type: "answer.correct", sourceId: "comparison-question" }, to: "summarize" },
          { on: { type: "answer.incorrect", sourceId: "comparison-question" }, to: "remediate" },
          { on: { type: "answer.attemptsExhausted", sourceId: "comparison-question" }, to: "summarize" },
        ],
      },
      {
        id: "remediate",
        enterActions: [
          { type: "disable", targetId: "comparison-question" },
          { type: "focus", target: { blockId: "case-video" } },
          { type: "playNarration", narrationId: "remediation" },
        ],
        transitions: [{ on: { type: "narration.ended", sourceId: "remediation" }, to: "wait-for-answer" }],
      },
      {
        id: "summarize",
        enterActions: [{ type: "clearFocus" }, { type: "playNarration", narrationId: "slice-summary" }],
        transitions: [{ on: { type: "narration.ended", sourceId: "slice-summary" }, to: "next" }],
      },
      {
        id: "next",
        enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }],
        transitions: [],
      },
    ],
  };
}

/** A full, valid SliceDefinition wrapping {@link sampleWorkflow} (used by the reducer tests). */
export function sampleSlice(): SliceDefinition {
  return {
    id: "slice-observe-and-answer",
    title: "Observe and answer",
    objectiveIds: ["obj-1"],
    estimatedSeconds: 300,
    blocks: [
      { id: "case-video", type: "video", source: "media/case.mp4" },
      {
        id: "comparison-question",
        type: "singleChoice",
        prompt: "Which option best explains the difference?",
        options: [
          { id: "a", label: "Option A" },
          { id: "b", label: "Option B" },
        ],
        assessment: { mode: "graded", correctOptionId: "a" },
        completion: { rule: "submit-correct-or-exhausted", maxAttempts: 2 },
      },
    ],
    layout: { preset: "full", slots: [{ id: "main", blockIds: ["case-video", "comparison-question"] }] },
    narrations: [
      { id: "introduce-video", text: "Watch this case.", audio: "audio/introduce-video.mp3" },
      { id: "introduce-question", text: "Now answer.", audio: "audio/introduce-question.mp3" },
      { id: "remediation", text: "Look again.", audio: "audio/remediation.mp3" },
      { id: "slice-summary", text: "Well done.", audio: "audio/slice-summary.mp3" },
    ],
    workflow: sampleWorkflow(),
    navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
  };
}
