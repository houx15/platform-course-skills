import { describe, it, expect } from "vitest";
import { COURSE_CONTRACT_VERSION } from "../src/index";

describe("course-contract package", () => {
  it("exposes a version constant", () => {
    expect(COURSE_CONTRACT_VERSION).toBe("0.0.0");
  });
});
