import "@testing-library/jest-dom";

// jsdom implements neither of these. `FocusManager`'s real-focus behavior
// (§Slice4 / P2-06) calls both unconditionally whenever a `focus` workflow
// effect fires, so every test that mounts a `SlicePlayer` — not just
// `focus.test.tsx` — needs a safe default, or scenes with `focus` effects in
// their fixtures (see `test/support/staticCourse.ts`) throw "not a function".
// Individual tests may still `vi.spyOn` these to assert call args.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
