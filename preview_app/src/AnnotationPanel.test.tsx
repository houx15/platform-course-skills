import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CourseDefinitionDocument } from "@mind-imprint/course-contract";
import { AnnotationPanel } from "./AnnotationPanel";

const document = {
  schemaVersion: "2.0",
  course: {
    id: "review-course",
    parts: [{
      id: "part-one",
      title: "Part one",
      slices: [{
        id: "slice-one",
        title: "Slice one",
        blocks: [{
          id: "image-gallery",
          type: "images",
          items: [{ id: "image-alpha", source: "assets/image.png", alt: "Example" }],
        }],
        workflow: { steps: [{ id: "show-gallery", action: "show", target: { blockId: "image-gallery" } }] },
      }, {
        id: "slice-two",
        title: "Slice two",
        blocks: [],
        workflow: { steps: [] },
      }],
    }],
  },
} as unknown as CourseDefinitionDocument;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("AnnotationPanel", () => {
  const existingAnnotation = {
    id: "annotation-existing-one",
    type: "content" as const,
    status: "open" as const,
    required: true,
    target: {
      courseId: "review-course",
      partId: "part-one",
      sliceId: "slice-one",
      blockId: "image-gallery",
      itemId: null,
      workflowStepId: null,
    },
    definitionHash: "a".repeat(64),
    text: "Make the caption clearer.",
    screenshotPath: null,
    createdAt: "2026-08-20T00:00:00.000Z",
    updatedAt: "2026-08-20T00:00:00.000Z",
    classification: null,
    proposedChange: null,
    resolutionDecisionId: null,
    appliedBlueprintHash: null,
    verifiedAgainstDefinitionHash: null,
    orphanReason: null,
    reboundFromDefinitionHash: null,
  };

  const otherSliceAnnotation = {
    ...existingAnnotation,
    id: "annotation-existing-two",
    target: { ...existingAnnotation.target, sliceId: "slice-two", blockId: null },
    text: "This belongs to the second page.",
  };

  it("saves an annotation against a stable item target", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") requests.push(init);
      return new Response(
        init?.method === "PUT" ? JSON.stringify({ ok: true }) : JSON.stringify({ schemaVersion: "1.0", annotations: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }));

    render(<AnnotationPanel document={document} definitionHash={"a".repeat(64)} sliceIndex={0} events={[]} visitedSliceIds={[]} runtimeErrors={[]} selectedTargetKey="item:image-gallery:image-alpha" />);
    await screen.findByText("课程预览与批注");
    fireEvent.change(screen.getByLabelText("具体批注"), { target: { value: "Please make this image larger." } });
    fireEvent.click(screen.getByRole("button", { name: "保存批注" }));

    await waitFor(() => expect(requests).toHaveLength(1));
    const payload = JSON.parse(String(requests[0]?.body));
    expect(payload.annotations[0].target).toMatchObject({
      courseId: "review-course",
      partId: "part-one",
      sliceId: "slice-one",
      blockId: "image-gallery",
      itemId: "image-alpha",
      workflowStepId: null,
    });
  });

  it("records explicit review evidence only after every Slice was visited", async () => {
    const posted: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") posted.push(init);
      return new Response(
        init?.method === "POST" ? JSON.stringify({ ok: true }) : JSON.stringify({ schemaVersion: "1.0", annotations: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }));

    render(
      <AnnotationPanel
        document={document}
        definitionHash={"a".repeat(64)}
        sliceIndex={0}
        visitedSliceIds={["slice-one", "slice-two"]}
        events={[{ id: "event-one", type: "student.continue", sourceId: "course-nav", sliceId: "slice-one" }]}
        runtimeErrors={[]}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "确认我已完整审查" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    const payload = JSON.parse(String(posted[0]?.body));
    expect(payload).toMatchObject({
      visitedSliceIds: ["slice-one", "slice-two"],
      teacherConfirmed: true,
      runtimeErrors: [],
    });
  });

  it("edits an existing annotation and reopens it for AI work", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") requests.push(init);
      return new Response(
        init?.method === "PUT"
          ? JSON.stringify({ ok: true })
          : JSON.stringify({ schemaVersion: "1.0", annotations: [existingAnnotation] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }));

    render(<AnnotationPanel document={document} definitionHash={"a".repeat(64)} sliceIndex={0} events={[]} visitedSliceIds={[]} runtimeErrors={[]} />);
    fireEvent.click(await screen.findByRole("button", { name: "修改批注" }));
    const editor = screen.getByLabelText("修改批注内容");
    expect(editor).toHaveValue("Make the caption clearer.");
    fireEvent.change(editor, { target: { value: "Make the evidence label clearer." } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => expect(requests).toHaveLength(1));
    const payload = JSON.parse(String(requests[0]?.body));
    expect(payload.annotations[0]).toMatchObject({
      id: "annotation-existing-one",
      text: "Make the evidence label clearer.",
      status: "open",
    });
  });

  it("marks an annotation complete, can reopen it, and can delete it", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") requests.push(init);
      return new Response(
        init?.method === "PUT"
          ? JSON.stringify({ ok: true })
          : JSON.stringify({ schemaVersion: "1.0", annotations: [existingAnnotation] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }));

    render(<AnnotationPanel document={document} definitionHash={"a".repeat(64)} sliceIndex={0} events={[]} visitedSliceIds={[]} runtimeErrors={[]} />);
    fireEvent.click(await screen.findByRole("button", { name: "标记已完成" }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(JSON.parse(String(requests[0]?.body)).annotations[0]).toMatchObject({
      status: "dismissed",
      resolutionDecisionId: "decision-complete-annotation-existing-one",
    });

    fireEvent.click(screen.getByRole("button", { name: "重新打开" }));
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(JSON.parse(String(requests[1]?.body)).annotations[0]).toMatchObject({
      status: "open",
      resolutionDecisionId: null,
    });

    fireEvent.click(screen.getByRole("button", { name: "删除批注" }));
    await waitFor(() => expect(requests).toHaveLength(3));
    expect(JSON.parse(String(requests[2]?.body)).annotations).toEqual([]);
  });

  it("shows current-page annotations by default and can reveal all Slice-labelled annotations", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ schemaVersion: "1.0", annotations: [existingAnnotation, otherSliceAnnotation] }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));

    render(<AnnotationPanel document={document} definitionHash={"a".repeat(64)} sliceIndex={0} events={[]} visitedSliceIds={[]} runtimeErrors={[]} />);

    expect(await screen.findByText("Make the caption clearer.")).toBeInTheDocument();
    expect(screen.getByText("slice-1 · Slice one")).toBeInTheDocument();
    expect(screen.queryByText("This belongs to the second page.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全部 · 2" }));
    expect(screen.getByText("This belongs to the second page.")).toBeInTheDocument();
    expect(screen.getByText("slice-2 · Slice two")).toBeInTheDocument();
  });
});
