import { describe, it, expect } from "vitest";
import { collectAssetPaths } from "../src/assets";
import type { CourseDefinitionDocument } from "../src/course";

// A synthetic document exercising every relativeAssetPathSchema-typed field.
// It need not pass full validation — collectAssetPaths only walks structure.
const doc = {
  schemaVersion: "2.0",
  course: {
    id: "c",
    title: "t",
    language: "en",
    estimatedMinutes: 5,
    objectives: [{ id: "o1", text: "x", evidenceBlockIds: ["b1"] }],
    opening: {
      learningPreview: [],
      personalization: { enabled: false, allowedSignals: [] },
      fallback: { text: "hi", audio: "assets/audio/open.mp3" },
    },
    closing: {
      preparedSummary: "s",
      takeaways: [],
      transferApplications: [],
      personalization: { enabled: false, allowedSignals: [] },
      fallback: { text: "bye", audio: "assets/audio/close.mp3" },
    },
    parts: [
      {
        id: "p1",
        title: "P",
        objectiveIds: ["o1"],
        slices: [
          {
            id: "s1",
            title: "S",
            objectiveIds: ["o1"],
            estimatedSeconds: 30,
            narrations: [{ id: "n1", text: "x", audio: "assets/audio/n1.mp3" }],
            blocks: [
              { id: "b1", type: "text", content: "no asset" },
              { id: "b2", type: "images", presentation: "single", items: [
                { id: "i1", source: "assets/images/a.png", alt: "a" },
                { id: "i2", source: "https://cdn.example/x.png", alt: "abs" }, // excluded
              ] },
              { id: "b3", type: "pdf", title: "P", source: "assets/pdfs/p.pdf" },
              { id: "b4", type: "video", source: "assets/videos/v.mp4",
                poster: "assets/images/poster.jpg", captions: "assets/captions/v.vtt",
                interaction: { source: "interactions/video/v.json" } },
              { id: "b5", type: "interactiveHtml", source: "interactions/html/sim.html",
                protocolVersion: "1.0", aspectRatio: "4:3" },
              { id: "b6", type: "images", presentation: "single", items: [
                { id: "i3", source: "assets/images/a.png", alt: "dup" }, // dedup
                { id: "i4", source: "data:image/png;base64,AAAA", alt: "inline" }, // excluded
              ] },
            ],
            layout: { kind: "full", slots: [] },
            workflow: {} as never,
            navigation: {} as never,
          },
        ],
      },
    ],
  },
} as unknown as CourseDefinitionDocument;

describe("collectAssetPaths", () => {
  it("returns every relative asset path, deduped, excluding absolute and data URIs", () => {
    const got = collectAssetPaths(doc).sort();
    expect(got).toEqual(
      [
        "assets/audio/close.mp3",
        "assets/audio/n1.mp3",
        "assets/audio/open.mp3",
        "assets/captions/v.vtt",
        "assets/images/a.png",
        "assets/images/poster.jpg",
        "assets/pdfs/p.pdf",
        "assets/videos/v.mp4",
        "interactions/html/sim.html",
        "interactions/video/v.json",
      ].sort(),
    );
  });
});
