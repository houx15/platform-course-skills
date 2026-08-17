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
      }],
    }],
  },
} as unknown as CourseDefinitionDocument;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("AnnotationPanel", () => {
  it("saves an annotation against a stable item target", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") requests.push(init);
      return new Response(
        init?.method === "PUT" ? JSON.stringify({ ok: true }) : JSON.stringify({ schemaVersion: "1.0", annotations: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }));

    render(<AnnotationPanel document={document} definitionHash={"a".repeat(64)} sliceIndex={0} events={[]} visitedSliceIds={[]} runtimeErrors={[]} />);
    await screen.findByText("课程预览与批注");
    fireEvent.change(screen.getByLabelText("批注目标"), { target: { value: "item:image-gallery:image-alpha" } });
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
        visitedSliceIds={["slice-one"]}
        events={[{ id: "event-one", type: "student.continue", sourceId: "course-nav", sliceId: "slice-one" }]}
        runtimeErrors={[]}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "确认我已完整审查" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    const payload = JSON.parse(String(posted[0]?.body));
    expect(payload).toMatchObject({
      visitedSliceIds: ["slice-one"],
      teacherConfirmed: true,
      runtimeErrors: [],
    });
  });
});
