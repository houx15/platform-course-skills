import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CourseDefinitionDocument } from "@mind-imprint/course-contract";
import { PreviewCoursePlayer } from "./PreviewCoursePlayer";

const previewApiMocks = vi.hoisted(() => ({
  loadAnnotations: vi.fn(),
  postInspectionObservation: vi.fn(),
  postPreviewEvidence: vi.fn(),
}));

vi.mock("./previewApi", () => previewApiMocks);

vi.mock("@mind-imprint/course-renderer", () => ({
  CoursePlayer: ({ onComplete }: { onComplete?: () => void }) => <div data-testid="course-player"><div data-block-id="case-question"><button type="button">Answer this question</button></div><button type="button" onClick={onComplete}>Complete course locally</button></div>,
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
  beforeEach(() => {
    previewApiMocks.loadAnnotations.mockReset().mockResolvedValue({ schemaVersion: "1.0", annotations: [] });
    previewApiMocks.postInspectionObservation.mockReset().mockResolvedValue({ ok: true });
    previewApiMocks.postPreviewEvidence.mockReset().mockResolvedValue(undefined);
  });

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

  it("ends locally without publishing and offers a clear publication handoff when no annotation is pending", async () => {
    render(<PreviewCoursePlayer document={document} definitionHash={"a".repeat(64)} />);

    fireEvent.click(screen.getByRole("button", { name: "Complete course locally" }));

    expect(screen.getByRole("status", { name: "本地预览已完成" })).toHaveTextContent("没有上传素材或发布课程");
    expect(await screen.findByRole("button", { name: "下一步：发布到学生端" })).toBeInTheDocument();
    expect(screen.queryByTestId("course-player")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一步：发布到学生端" }));
    await waitFor(() => expect(previewApiMocks.postPreviewEvidence).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status", { name: "本地预览已完成" })).toHaveTextContent("正式上传前仍会展示发布计划");
  });

  it("keeps pending annotations under teacher control without adding a new publication restriction", async () => {
    previewApiMocks.loadAnnotations.mockResolvedValue({
      schemaVersion: "1.0",
      annotations: [{ id: "annotation-one", status: "open" }],
    });
    render(<PreviewCoursePlayer document={document} definitionHash={"a".repeat(64)} />);

    fireEvent.click(screen.getByRole("button", { name: "Complete course locally" }));

    expect(await screen.findByText("还有 1 条批注。你可以检查、修改、标记完成或继续进入发布确认。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一步：发布到学生端" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开批注栏" }));
    expect(screen.getByLabelText("课程批注")).toBeInTheDocument();
  });

  it("permits direct paging and keeps annotations available but collapsed in inspection mode", async () => {
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
    expect(screen.getByRole("button", { name: "打开课程批注" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("课程批注")).not.toBeInTheDocument();
    expect(screen.getByLabelText("学生端课程预览").parentElement).toHaveClass("preview-shell--inspection");
  });
});
