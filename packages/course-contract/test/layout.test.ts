import { describe, it, expect } from "vitest";
import { LayoutDefinition } from "../src/layout";

const splitH = {
  preset: "split-horizontal",
  ratio: "2:1",
  slots: [ { id: "left", blockIds: ["v"] }, { id: "right", blockIds: ["q"] } ],
};

describe("LayoutDefinition", () => {
  it("parses a split-horizontal with a ratio and canonical slots", () => {
    expect(LayoutDefinition.safeParse(splitH).success).toBe(true);
  });
  it("rejects split-horizontal without a ratio", () => {
    const { ratio, ...noRatio } = splitH;
    expect(LayoutDefinition.safeParse(noRatio).success).toBe(false);
  });
  it("accepts the weighted ratios (3:2, 2:3, 3:1, 1:3) and rejects an out-of-set ratio", () => {
    for (const ratio of ["1:1", "3:2", "2:3", "2:1", "1:2", "3:1", "1:3"]) {
      expect(LayoutDefinition.safeParse({ ...splitH, ratio }).success).toBe(true);
    }
    expect(LayoutDefinition.safeParse({ ...splitH, ratio: "5:1" }).success).toBe(false);
    expect(LayoutDefinition.safeParse({ ...splitH, ratio: "3" }).success).toBe(false);
  });
  it("rejects split-horizontal with wrong slot ids", () => {
    const bad = { ...splitH, slots: [ { id: "top", blockIds: ["v"] }, { id: "bottom", blockIds: ["q"] } ] };
    expect(LayoutDefinition.safeParse(bad).success).toBe(false);
  });
  it("accepts a full layout with the single main slot", () => {
    expect(LayoutDefinition.safeParse({ preset: "full", slots: [ { id: "main", blockIds: ["t"] } ] }).success).toBe(true);
  });
  it("accepts grid with 2–4 cells, rejects 1 or 5", () => {
    const cells = (n: number) => ({ preset: "grid", slots: Array.from({ length: n }, (_, i) => ({ id: `cell-${i + 1}`, blockIds: [] })) });
    expect(LayoutDefinition.safeParse(cells(2)).success).toBe(true);
    expect(LayoutDefinition.safeParse(cells(4)).success).toBe(true);
    expect(LayoutDefinition.safeParse(cells(1)).success).toBe(false);
    expect(LayoutDefinition.safeParse(cells(5)).success).toBe(false);
  });
});
