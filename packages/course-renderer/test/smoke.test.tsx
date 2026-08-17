import { render, screen } from "@testing-library/react";
import { COURSE_RENDERER_VERSION } from "../src/index";

describe("course-renderer smoke", () => {
  it("mounts a div via RTL", () => {
    render(<div data-testid="smoke">hello</div>);
    expect(screen.getByTestId("smoke")).toBeInTheDocument();
  });

  it("exposes the package version", () => {
    expect(COURSE_RENDERER_VERSION).toBe("0.0.0");
  });
});
