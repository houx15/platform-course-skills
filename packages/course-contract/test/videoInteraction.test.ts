import { describe, it, expect } from "vitest";
import {
  VideoInteractionDocument,
  validateVideoInteraction,
} from "../src/videoInteraction";

/** The §14 example document. */
const example = {
  schemaVersion: "1.1",
  video: {
    blockId: "case-video",
    source: "assets/videos/case.mp4",
    durationSeconds: 195,
    cues: [
      {
        id: "prediction-check",
        atSeconds: 42,
        pauseVideo: true,
        required: true,
        prompt: "What do you predict will happen next?",
        activity: {
          type: "singleChoice",
          options: [
            { id: "same-basis", label: "The comparison basis will stay the same" },
            { id: "new-basis", label: "The comparison basis will change" },
          ],
          assessment: { mode: "survey" },
          completion: { rule: "submit-any" },
        },
      },
    ],
  },
};

/** The owning VideoBlock the interaction document references. */
const owningVideoBlock = {
  id: "case-video",
  type: "video" as const,
  source: "assets/videos/case.mp4",
  durationSeconds: 195,
};

describe("VideoInteractionDocument schema", () => {
  it("parses the §14 example", () => {
    expect(VideoInteractionDocument.safeParse(example).success).toBe(true);
  });

  it("rejects unknown properties (strict)", () => {
    const bad = { ...example, extra: 1 };
    expect(VideoInteractionDocument.safeParse(bad).success).toBe(false);
  });

  it("rejects a wrong schemaVersion", () => {
    const bad = { ...example, schemaVersion: "1.0" };
    expect(VideoInteractionDocument.safeParse(bad).success).toBe(false);
  });

  it("parses a fillBlank cue activity", () => {
    const doc = {
      ...example,
      video: {
        ...example.video,
        cues: [
          {
            id: "recall",
            atSeconds: 30,
            pauseVideo: true,
            required: false,
            prompt: "Name the comparison basis.",
            activity: {
              type: "fillBlank",
              assessment: { mode: "graded", acceptedAnswers: ["method"] },
              completion: { rule: "submit-correct" },
            },
          },
        ],
      },
    };
    expect(VideoInteractionDocument.safeParse(doc).success).toBe(true);
  });

  it("rejects an unknown activity type", () => {
    const doc = {
      ...example,
      video: {
        ...example.video,
        cues: [
          {
            ...example.video.cues[0],
            activity: { type: "drawing" },
          },
        ],
      },
    };
    expect(VideoInteractionDocument.safeParse(doc).success).toBe(false);
  });
});

describe("validateVideoInteraction (referential, §14)", () => {
  it("returns no issues for the valid example against its owning block", () => {
    const parsed = VideoInteractionDocument.parse(example);
    expect(validateVideoInteraction(parsed, owningVideoBlock)).toEqual([]);
  });

  it("flags duplicate cue ids", () => {
    const doc = VideoInteractionDocument.parse({
      ...example,
      video: {
        ...example.video,
        cues: [
          { ...example.video.cues[0], id: "dup", atSeconds: 10 },
          { ...example.video.cues[0], id: "dup", atSeconds: 20 },
        ],
      },
    });
    const issues = validateVideoInteraction(doc, owningVideoBlock);
    expect(issues.some((i) => /duplicate cue id/.test(i.message))).toBe(true);
  });

  it("flags non-increasing cue times", () => {
    const doc = VideoInteractionDocument.parse({
      ...example,
      video: {
        ...example.video,
        cues: [
          { ...example.video.cues[0], id: "a", atSeconds: 40 },
          { ...example.video.cues[0], id: "b", atSeconds: 40 },
        ],
      },
    });
    const issues = validateVideoInteraction(doc, owningVideoBlock);
    expect(issues.some((i) => /strictly increasing/.test(i.message))).toBe(true);
  });

  it("flags a cue time beyond the video duration", () => {
    const doc = VideoInteractionDocument.parse({
      ...example,
      video: {
        ...example.video,
        cues: [{ ...example.video.cues[0], id: "late", atSeconds: 500 }],
      },
    });
    const issues = validateVideoInteraction(doc, owningVideoBlock);
    expect(issues.some((i) => /duration/.test(i.message))).toBe(true);
  });

  it("flags a blockId mismatch vs the owning block", () => {
    const doc = VideoInteractionDocument.parse({
      ...example,
      video: { ...example.video, blockId: "other-video" },
    });
    const issues = validateVideoInteraction(doc, owningVideoBlock);
    expect(issues.some((i) => /blockId/.test(i.message))).toBe(true);
  });

  it("flags a source mismatch vs the owning block", () => {
    const doc = VideoInteractionDocument.parse({
      ...example,
      video: { ...example.video, source: "assets/videos/other.mp4" },
    });
    const issues = validateVideoInteraction(doc, owningVideoBlock);
    expect(issues.some((i) => /source/.test(i.message))).toBe(true);
  });

  it("all issues are tagged as the referential layer", () => {
    const doc = VideoInteractionDocument.parse({
      ...example,
      video: { ...example.video, blockId: "other-video" },
    });
    const issues = validateVideoInteraction(doc, owningVideoBlock);
    expect(issues.every((i) => i.layer === "referential")).toBe(true);
  });
});
