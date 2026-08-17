import { render } from "@testing-library/react";
import { FocusProvider, FocusTarget, focusedItemIdFor, isBlockFocused } from "../src/focus/FocusManager";
import type { TargetRef } from "@mind-imprint/course-contract";

function renderTree(focus: TargetRef | null) {
  return render(
    <FocusProvider value={focus}>
      <FocusTarget blockId="a">block a</FocusTarget>
      <FocusTarget blockId="img">img block</FocusTarget>
      <FocusTarget blockId="img" itemId="x">
        item x
      </FocusTarget>
      <FocusTarget blockId="img" itemId="y">
        item y
      </FocusTarget>
    </FocusProvider>,
  );
}

const focused = (c: HTMLElement) => [...c.querySelectorAll('[data-focused="true"]')];

describe("FocusManager", () => {
  it("block-level focus marks the matching block wrapper", () => {
    const { container } = renderTree({ blockId: "a" });
    const marked = focused(container);
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveAttribute("data-focus-block", "a");
    expect(marked[0]).toHaveClass("course-focus-ring");
  });

  it("item focus marks only the matching item, not the block", () => {
    const { container } = renderTree({ blockId: "img", itemId: "x" });
    const marked = focused(container);
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveAttribute("data-focus-item", "x");
  });

  it("clearFocus (null) removes all focus", () => {
    const { container } = renderTree(null);
    expect(focused(container)).toHaveLength(0);
  });

  it("pure helpers agree with the wrappers", () => {
    expect(isBlockFocused({ blockId: "a" }, "a")).toBe(true);
    expect(isBlockFocused({ blockId: "a", itemId: "x" }, "a")).toBe(false);
    expect(focusedItemIdFor({ blockId: "img", itemId: "x" }, "img")).toBe("x");
    expect(focusedItemIdFor({ blockId: "img" }, "img")).toBeUndefined();
    expect(focusedItemIdFor(null, "img")).toBeUndefined();
  });
});

// §Slice4 / P2-06 — focus is real DOM focus (not visual metadata only): the
// matching wrapper receives keyboard/AT focus, scrolls into view, and carries
// the visible ring. jsdom implements neither `scrollIntoView` nor
// `matchMedia`; `test/setup.ts` installs safe defaults so every renderer test
// (not just this file) can mount a `focus`-effect scene without throwing —
// here we spy on those defaults to assert the real calls.
describe("FocusManager — real accessible focus (§P2-06)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("a matched focus target receives real DOM focus and the ring class", () => {
    const { container } = renderTree({ blockId: "a" });
    const target = container.querySelector('[data-focus-block="a"]');
    expect(target).toHaveClass("course-focus-ring");
    expect(document.activeElement).toBe(target);
  });

  it("scrolls the matched target into view, nearest, non-reduced-motion default = smooth", () => {
    const scrollSpy = vi.spyOn(Element.prototype, "scrollIntoView");
    const { container } = renderTree({ blockId: "img", itemId: "x" });
    const target = container.querySelector('[data-focus-item="x"]');
    expect(document.activeElement).toBe(target);
    expect(scrollSpy).toHaveBeenCalledWith({ block: "nearest", behavior: "smooth" });
  });

  it("respects prefers-reduced-motion — scrolls without smooth animation", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        }) as MediaQueryList,
    );
    const scrollSpy = vi.spyOn(Element.prototype, "scrollIntoView");
    renderTree({ blockId: "a" });
    expect(scrollSpy).toHaveBeenCalledWith({ block: "nearest", behavior: "auto" });
  });

  // §Slice5 review nit (P2-06 fold) — Slice 4 put `tabIndex={-1}` + a
  // machine-id `aria-label` on EVERY block wrapper. Only the actively-focused
  // wrapper gets programmatic focusability, and its accessible name comes
  // from a caller-supplied meaningful `label` (block content/title) — never
  // a raw internal id, and omitted entirely when the caller has none.
  it("omits aria-label when no meaningful label is given — never announces the raw internal id", () => {
    const { container } = renderTree({ blockId: "img", itemId: "x" });
    const target = container.querySelector('[data-focus-item="x"]');
    expect(target).not.toHaveAttribute("aria-label");
  });

  it("uses a caller-supplied meaningful label as the accessible name when the target is focused", () => {
    const { container } = render(
      <FocusProvider value={{ blockId: "a" }}>
        <FocusTarget blockId="a" label="两个结论能直接比较吗？">
          block a
        </FocusTarget>
      </FocusProvider>,
    );
    const target = container.querySelector('[data-focus-block="a"]');
    expect(target).toHaveAttribute("aria-label", "两个结论能直接比较吗？");
  });

  it("only the focused wrapper is a programmatic focus target — non-focused wrappers carry no tabIndex", () => {
    const { container } = renderTree({ blockId: "a" });
    const focusedEl = container.querySelector('[data-focus-block="a"]');
    expect(focusedEl).toHaveAttribute("tabindex", "-1");
    const others = [...container.querySelectorAll("[data-focus-block]")].filter((el) => el !== focusedEl);
    expect(others.length).toBeGreaterThan(0);
    for (const el of others) {
      expect(el).not.toHaveAttribute("tabindex");
      expect(el).not.toHaveAttribute("aria-label");
    }
  });

  it("a not-visible target is aria-hidden (its box reservation is the stylesheet's job — §Slice5 / P1-06)", () => {
    const { container } = render(
      <FocusProvider value={null}>
        <FocusTarget blockId="a" visible={false}>
          block a
        </FocusTarget>
      </FocusProvider>,
    );
    const target = container.querySelector('[data-focus-block="a"]');
    expect(target).toHaveAttribute("aria-hidden", "true");
  });

  it("clearFocus (focus -> null) blurs the previously-focused target and drops the ring", () => {
    const { container, rerender } = render(
      <FocusProvider value={{ blockId: "a" }}>
        <FocusTarget blockId="a">block a</FocusTarget>
      </FocusProvider>,
    );
    const target = container.querySelector('[data-focus-block="a"]');
    expect(document.activeElement).toBe(target);

    rerender(
      <FocusProvider value={null}>
        <FocusTarget blockId="a">block a</FocusTarget>
      </FocusProvider>,
    );
    expect(target).not.toHaveClass("course-focus-ring");
    expect(target).not.toHaveAttribute("data-focused");
    expect(document.activeElement).not.toBe(target);
  });

  it("moving focus from one target to another blurs the old one and focuses the new one", () => {
    const { container, rerender } = render(
      <FocusProvider value={{ blockId: "a" }}>
        <FocusTarget blockId="a">block a</FocusTarget>
        <FocusTarget blockId="b">block b</FocusTarget>
      </FocusProvider>,
    );
    const targetA = container.querySelector('[data-focus-block="a"]');
    const targetB = container.querySelector('[data-focus-block="b"]');
    expect(document.activeElement).toBe(targetA);

    rerender(
      <FocusProvider value={{ blockId: "b" }}>
        <FocusTarget blockId="a">block a</FocusTarget>
        <FocusTarget blockId="b">block b</FocusTarget>
      </FocusProvider>,
    );
    expect(document.activeElement).toBe(targetB);
    expect(targetA).not.toHaveClass("course-focus-ring");
    expect(targetB).toHaveClass("course-focus-ring");
  });
});
