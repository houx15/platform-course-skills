import type { CourseDefinitionDocument, SliceDefinition } from "@mind-imprint/course-contract";

/**
 * A small, fully-valid static course used to prove the renderer end-to-end.
 * Two slices in one part:
 *  - slice-one (full layout): intro narration → reveal a hidden text block +
 *    enable a continue control → student.continue → completeSlice + navigate.
 *  - slice-two (split-horizontal 2:1, text + images): intro narration →
 *    narration.ended → completeSlice + navigate.
 * Global block ids are slice-prefixed (contract requires course-wide uniqueness).
 */

export const sliceOne: SliceDefinition = {
  id: "slice-one",
  title: "第一片段",
  objectiveIds: ["obj-one"],
  estimatedSeconds: 120,
  blocks: [
    { id: "s1-intro-text", type: "text", content: "# 欢迎\n这是**第一段**讲解。" },
    { id: "s1-reveal-text", type: "text", content: "这段文字在讲解结束后才出现。" },
    { id: "s1-continue", type: "text", content: "准备好后继续。" },
  ],
  layout: { preset: "full", slots: [{ id: "main", blockIds: ["s1-intro-text", "s1-reveal-text", "s1-continue"] }] },
  narrations: [{ id: "s1-narration", text: "第一段讲解的文字稿。", audio: "audio/s1.mp3" }],
  workflow: {
    version: "1.0",
    initialStepId: "intro",
    initialState: {
      visibleBlockIds: ["s1-intro-text", "s1-continue"],
      enabledBlockIds: ["s1-intro-text"],
    },
    steps: [
      {
        id: "intro",
        enterActions: [{ type: "playNarration", narrationId: "s1-narration" }],
        transitions: [{ on: { type: "narration.ended", sourceId: "s1-narration" }, to: "reveal" }],
      },
      {
        id: "reveal",
        enterActions: [
          { type: "show", targetId: "s1-reveal-text" },
          { type: "enable", targetId: "s1-continue" },
        ],
        transitions: [{ on: { type: "student.continue" }, to: "done" }],
      },
      {
        id: "done",
        enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }],
        transitions: [],
      },
    ],
  },
  navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
};

export const sliceTwo: SliceDefinition = {
  id: "slice-two",
  title: "第二片段",
  objectiveIds: ["obj-one"],
  estimatedSeconds: 90,
  blocks: [
    { id: "s2-text", type: "text", content: "看看右边的图片。" },
    {
      id: "s2-images",
      type: "images",
      presentation: "side-by-side",
      items: [
        { id: "s2-img-a", source: "img/a.png", alt: "图 A" },
        { id: "s2-img-b", source: "img/b.png", alt: "图 B" },
      ],
    },
  ],
  layout: {
    preset: "split-horizontal",
    ratio: "2:1",
    slots: [
      { id: "left", blockIds: ["s2-text"] },
      { id: "right", blockIds: ["s2-images"] },
    ],
  },
  narrations: [{ id: "s2-narration", text: "第二段讲解的文字稿。", audio: "audio/s2.mp3" }],
  workflow: {
    version: "1.0",
    initialStepId: "intro",
    steps: [
      {
        id: "intro",
        enterActions: [{ type: "playNarration", narrationId: "s2-narration" }],
        transitions: [{ on: { type: "narration.ended", sourceId: "s2-narration" }, to: "done" }],
      },
      {
        id: "done",
        enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }],
        transitions: [],
      },
    ],
  },
  navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
};

/**
 * §15 golden assessment slice: a graded single-choice question drives workflow
 * branching. `wait-for-answer` fans out to three targets —
 *   answer.correct → summarize, answer.incorrect → remediate → back,
 *   answer.attemptsExhausted → summarize — proving the renderer's Events actually
 * steer WorkflowRuntime through SlicePlayer. Not added to the document above so
 * it can't disturb the CoursePlayer navigation test; the branching test mounts
 * it directly. Block ids are `as-`-prefixed to stay course-wide unique.
 */
export const assessmentSlice: SliceDefinition = {
  id: "assessment-slice",
  title: "观察并作答",
  objectiveIds: ["obj-one"],
  estimatedSeconds: 120,
  blocks: [
    { id: "as-lead", type: "text", content: "先观察两个论断如何定义各自的证据。" },
    {
      id: "as-question",
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
      completion: { rule: "submit-correct-or-exhausted", maxAttempts: 2 },
    },
  ],
  layout: { preset: "full", slots: [{ id: "main", blockIds: ["as-lead", "as-question"] }] },
  narrations: [
    { id: "as-intro", text: "现在判断两个结论能否直接比较。", audio: "audio/as-intro.mp3" },
    { id: "as-remediation", text: "再看看对象、时间范围与方法。", audio: "audio/as-remediation.mp3" },
    { id: "as-summary", text: "比较结论前，先确认证据确实可比。", audio: "audio/as-summary.mp3" },
  ],
  workflow: {
    version: "1.0",
    initialStepId: "introduce-question",
    initialState: {
      visibleBlockIds: ["as-lead", "as-question"],
      enabledBlockIds: [],
    },
    steps: [
      {
        id: "introduce-question",
        enterActions: [
          { type: "focus", target: { blockId: "as-question" } },
          { type: "playNarration", narrationId: "as-intro" },
        ],
        transitions: [{ on: { type: "narration.ended", sourceId: "as-intro" }, to: "wait-for-answer" }],
      },
      {
        id: "wait-for-answer",
        enterActions: [{ type: "enable", targetId: "as-question" }],
        transitions: [
          { on: { type: "answer.correct", sourceId: "as-question" }, to: "summarize" },
          { on: { type: "answer.incorrect", sourceId: "as-question" }, to: "remediate" },
          { on: { type: "answer.attemptsExhausted", sourceId: "as-question" }, to: "summarize" },
        ],
      },
      {
        id: "remediate",
        enterActions: [
          { type: "disable", targetId: "as-question" },
          { type: "focus", target: { blockId: "as-lead" } },
          { type: "playNarration", narrationId: "as-remediation" },
        ],
        transitions: [{ on: { type: "narration.ended", sourceId: "as-remediation" }, to: "wait-for-answer" }],
      },
      {
        id: "summarize",
        enterActions: [{ type: "clearFocus" }, { type: "playNarration", narrationId: "as-summary" }],
        transitions: [{ on: { type: "narration.ended", sourceId: "as-summary" }, to: "next" }],
      },
      {
        id: "next",
        enterActions: [{ type: "completeSlice" }, { type: "navigate", target: "nextSlice" }],
        transitions: [],
      },
    ],
  },
  navigation: { previous: "allowed", manualNext: "after-completion", autoNext: true, revisit: "restore-completed-state" },
};

export const ASSESSMENT_PART_ID = "part-one";

export const staticCourseDocument: CourseDefinitionDocument = {
  schemaVersion: "2.0",
  course: {
    id: "static-demo-course",
    title: "静态演示课程",
    language: "zh-CN",
    estimatedMinutes: 5,
    objectives: [{ id: "obj-one", text: "理解演示流程", evidenceBlockIds: ["s1-intro-text"] }],
    opening: {
      learningPreview: ["认识片段流转", "看到讲解与揭示"],
      personalization: { enabled: false, allowedSignals: [] },
      fallback: { text: "欢迎来到这门演示课程，我们一起开始吧。" },
    },
    parts: [
      {
        id: "part-one",
        title: "唯一章节",
        objectiveIds: ["obj-one"],
        slices: [sliceOne, sliceTwo],
      },
    ],
    closing: {
      preparedSummary: "你走完了两个片段，理解了演示流程。",
      takeaways: ["片段按顺序推进", "讲解结束触发揭示"],
      transferApplications: ["把这种节奏用到真实课程里"],
      personalization: { enabled: false, allowedSignals: [] },
      fallback: { text: "这门演示课程到此结束，做得好。" },
    },
  },
};

export const STATIC_PART_ID = "part-one";
