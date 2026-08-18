import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CourseDefinitionDocument } from "@mind-imprint/course-contract";
import { PreviewCoursePlayer } from "./PreviewCoursePlayer";

vi.mock("@mind-imprint/course-renderer", () => ({
  CoursePlayer: () => <div data-testid="course-player">Student course</div>,
  InteractionLoaderProvider: ({ children }: { children: React.ReactNode }) => children,
  AudioEngineProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("./AnnotationPanel", () => ({
  AnnotationPanel: () => <aside aria-label="课程批注">Annotations</aside>,
}));

vi.mock("./previewAdapters", () => ({
  createPreviewAdapters: () => ({}),
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
});
