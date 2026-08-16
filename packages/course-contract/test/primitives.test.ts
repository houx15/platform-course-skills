import { describe, it, expect } from "vitest";
import { idSchema, relativeAssetPathSchema } from "../src/primitives";

describe("idSchema", () => {
  it("accepts lower-case hyphenated ids", () => {
    expect(idSchema.safeParse("slice-observe-1").success).toBe(true);
  });
  it("rejects upper-case, spaces, leading/trailing/double hyphens", () => {
    for (const bad of ["Slice", "a b", "-a", "a-", "a--b", ""]) {
      expect(idSchema.safeParse(bad).success).toBe(false);
    }
  });
});

describe("relativeAssetPathSchema", () => {
  it("accepts safe relative paths", () => {
    expect(relativeAssetPathSchema.safeParse("assets/audio/intro.mp3").success).toBe(true);
  });
  it("rejects absolute, parent-traversal, scheme, and backslash paths", () => {
    for (const bad of ["/assets/x.png", "../secret", "a/../b", "https://x/y.png", "a\\b", ""]) {
      expect(relativeAssetPathSchema.safeParse(bad).success).toBe(false);
    }
  });
});
