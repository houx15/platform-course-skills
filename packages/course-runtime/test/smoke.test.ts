import { describe, it, expect } from "vitest";
import { COURSE_RUNTIME_VERSION } from "../src/index";

describe("course-runtime smoke", () => {
  it("exposes the package version", () => {
    expect(COURSE_RUNTIME_VERSION).toBe("0.0.0");
  });
});
