import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CourseDefinitionDocument } from "@mind-imprint/course-contract";
import { PreviewCoursePlayer } from "./PreviewCoursePlayer";

vi.mock("@mind-imprint/course-renderer", () => ({
  CoursePlayer: () => <div data-testid="course-player"><div data-block-id="case-question"><button type="button">Answer this question</button></div></div>,
  InteractionLoaderProvider: ({ children }: { children: React.ReactNode }) => children,
  AudioEngineProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("./AnnotationPanel", () => ({
  AnnotationPanel: ({ selectedTargetKey }: { selectedTargetKey?: string | null }) => <aside aria-label="课程批注">Selected: {selectedTargetKey ?? "slice"}</aside>,
}));

vi.mock("./previewAdapters", () => ({
  createPreviewAdapters: () => ({
    sessionAdapter: {
      create: async () => ({ id: "inspection-session" }),
      setStatus: async () => undefined,
      setCurrent: async () => undefined,
      setDefinitionHash: async () => undefined,
    },
  }),
  loadVideoInteraction: vi.fn(),
  SilentPreviewAudioEngine: class {},
}));

const document = {
  schemaVersion: "2.0",
  course: {
    id: "preview-layout-course",
    parts: [{
      id: "part-one",
      title: "Part one",
      slices: [{ id: "slice-one", title: "Slice one", blocks: [], workflow: { steps: [] } }],
    }],
  },
} as unknown as CourseDefinitionDocument;

describe("PreviewCoursePlayer", () => {
  it("matches the student sidebar's collapsed and expanded widths", () => {
    render(<PreviewCoursePlayer document={document} definitionHash={"a".repeat(64)} />);

    expect(screen.getByLabelText("学生端课程预览")).toBeInTheDocument();
    expect(screen.queryByLabelText("课程批注")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "打开课程批注" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.parentElement).toHaveStyle({ width: "46px" });
    fireEvent.click(toggle);

    expect(screen.getByLabelText("课程批注")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭课程批注" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "关闭课程批注" }).parentElement).toHaveStyle({ width: "330px" });
  });

  it("selects a rendered component as the annotation target by clicking it", () => {
    render(<PreviewCoursePlayer document={document} definitionHash={"a".repeat(64)} />);
    fireEvent.click(screen.getByRole("button", { name: "打开课程批注" }));

    fireEvent.click(screen.getByRole("button", { name: "Answer this question" }));
    expect(screen.getByLabelText("课程批注")).toHaveTextContent("Selected: slice");

    fireEvent.click(screen.getByRole("button", { name: "开启点选批注" }));
    expect(screen.getByRole("button", { name: "关闭点选批注" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Answer this question" }));

    expect(screen.getByLabelText("课程批注")).toHaveTextContent("Selected: block:case-question");
  });

  it("uses the full renderer surface, permits direct paging, and hides annotations in inspection mode", async () => {
    render(<PreviewCoursePlayer
      document={document}
      definitionHash={"a".repeat(64)}
      inspection={{
        inspection: true,
        nonce: "inspection-launch",
        definitionHash: "a".repeat(64),
        expectedStates: ["part-one/slice-one/default"],
      }}
    />);

    expect(await screen.findByTestId("course-player")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("检查模式 · 1 / 1");
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "打开课程批注" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("学生端课程预览").parentElement).toHaveClass("preview-shell--inspection");
  });
});
