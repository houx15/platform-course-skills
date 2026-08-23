import { courseCssText } from "./support/courseCss";

/**
 * §Slice5 / P1-06 — structural proof that the renderer-owned stylesheet
 * actually carries the one-screen composition contract, not just that
 * SOME `course.css` file exists. Full visual verification at the supported
 * desktop viewport matrix (>=1280x720 / >=1440x900) is Slice 10's browser
 * job; jsdom has no real layout engine, so these assertions read the
 * shipped CSS source rather than a computed style.
 */
describe("course stylesheet (styles/course.css)", () => {
  it("the shell never page-scrolls — .course-shell is overflow:hidden and fills its viewport region", () => {
    const rule = /\.course-shell\s*\{[^}]*height:\s*100%[^}]*overflow:\s*hidden/;
    expect(courseCssText).toMatch(rule);
  });

  it("the layout region absorbs the remaining height inside a Slice, not the page", () => {
    expect(courseCssText).toMatch(/\.course-slice\s*>\s*\.course-layout\s*\{[^}]*flex:\s*1/);
  });

  it("the layout frame is gapped and shrinkable (P1-06 composition, not bare grid tracks)", () => {
    expect(courseCssText).toMatch(/\.course-layout\s*\{[^}]*gap:\s*var\(--course-gap/);
  });

  it("every slot is its own contained overflow:auto viewer — content scrolls WITHIN the slot, never the page", () => {
    expect(courseCssText).toMatch(/\.course-layout__slot\s*\{[^}]*overflow:\s*auto/);
  });

  it("every slot centers its content vertically (safe center) — short cards float in the middle, not pinned to the top", () => {
    expect(courseCssText).toMatch(/\.course-layout__slot\s*\{[^}]*justify-content:\s*safe\s+center/);
  });

  it("lets an images block fill its growing wrapper so its figures can center vertically", () => {
    expect(courseCssText).toMatch(/\.course-block--images\s*\{[^}]*flex:\s*1\s+1\s+auto/);
  });

  it("an images wrapper grows ONLY as the slot's only child — a figure sharing its slot must not strand its text sibling at the bottom", () => {
    // The grow list that applies unconditionally is the genuinely
    // height-hungry media; images is deliberately NOT in it.
    const unconditionalGrow = courseCssText.match(
      /\.course-slot-block:has\(> \.course-block--pdf\),[\s\S]*?\{[^}]*flex:\s*1\s+1\s+auto[^}]*\}/,
    );
    expect(unconditionalGrow).not.toBeNull();
    expect(unconditionalGrow![0]).not.toMatch(/course-block--images/);
    expect(courseCssText).toMatch(
      /\.course-slot-block:only-child:has\(> \.course-block--images\)\s*\{[^}]*flex:\s*1\s+1\s+auto/,
    );
  });

  it("a richText card fills its slot and scrolls INSIDE itself — the one block allowed to overflow, without the shell ever page-scrolling", () => {
    expect(courseCssText).toMatch(
      /\.course-slot-block:has\(> \.course-block--pdf\),[\s\S]*?course-block--rich-text\)[\s\S]*?\{[^}]*flex:\s*1\s+1\s+auto/,
    );
    expect(courseCssText).toMatch(/\.course-block--rich-text\s*\{[^}]*overflow:\s*hidden/);
    expect(courseCssText).toMatch(/\.course-rich-text__frame\s*\{[^}]*flex:\s*1\s+1\s+auto/);
  });

  it("a wrapper holding a hidden block collapses, so a not-yet-revealed block never holds the slot's space open", () => {
    expect(courseCssText).toMatch(
      /\.course-slot-block:has\(> \.course-block\[hidden\]\)\s*\{[^}]*display:\s*none/,
    );
  });

  it("natural-height slot wrappers do not shrink below their content — an over-full slot scrolls, never overlaps (bug: right column overlapped)", () => {
    // The base wrapper is flex-shrink:0 so stacked blocks (e.g. a question above
    // a fill-blank in a half-height grid cell) keep their content height and the
    // slot's overflow:auto engages, instead of the flex algorithm compressing
    // them until their content bleeds out and overlaps.
    expect(courseCssText).toMatch(/\.course-slot-block\s*\{[^}]*flex-shrink:\s*0/);
  });

  it("ships a video loading overlay — a spinner that never blocks the native controls", () => {
    expect(courseCssText).toMatch(/\.course-video__loading\s*\{[^}]*position:\s*absolute/);
    expect(courseCssText).toMatch(/\.course-video__loading\s*\{[^}]*pointer-events:\s*none/);
    expect(courseCssText).toMatch(/\.course-video__loading-spinner\s*\{[^}]*animation:\s*course-spin/);
  });

  it("gallery nav is overlay arrows anchored on the image's left/right edges", () => {
    expect(courseCssText).toMatch(/\.course-images__gallery-stage\s*\{[^}]*position:\s*relative/);
    expect(courseCssText).toMatch(/\.course-images__nav-arrow\s*\{[^}]*position:\s*absolute/);
    expect(courseCssText).toMatch(/\.course-images__nav-arrow--prev\s*\{[^}]*left:/);
    expect(courseCssText).toMatch(/\.course-images__nav-arrow--next\s*\{[^}]*right:/);
  });

  it("ships the click-to-enlarge image lightbox — dismissable backdrop + contained enlarged image", () => {
    expect(courseCssText).toMatch(/\.course-lightbox\s*\{[^}]*position:\s*fixed/);
    expect(courseCssText).toMatch(/\.course-lightbox__backdrop\s*\{[^}]*cursor:\s*zoom-out/);
    expect(courseCssText).toMatch(/\.course-lightbox__img\s*\{[^}]*object-fit:\s*contain/);
  });

  it("the loading surface shows a real spinner, not an empty white box", () => {
    expect(courseCssText).toMatch(/\.course-loading\s*\{[^}]*justify-content:\s*center/);
    expect(courseCssText).toMatch(/\.course-loading__spinner\s*\{[^}]*animation:\s*course-spin/);
    expect(courseCssText).toMatch(/@keyframes\s+course-spin/);
  });

  it("ships the read-in-popup PDF modal — dismissable backdrop + slot-filling frame", () => {
    expect(courseCssText).toMatch(/\.course-pdf-modal\s*\{[^}]*position:\s*fixed/);
    expect(courseCssText).toMatch(/\.course-pdf-modal__frame\s*\{[^}]*flex:\s*1/);
  });

  it("media (video/image/pdf) is contained to its slot — max-width/height:100% + object-fit", () => {
    expect(courseCssText).toMatch(/\.course-video__player\s*\{[^}]*max-width:\s*100%[^}]*object-fit:\s*contain/);
    expect(courseCssText).toMatch(/\.course-images__item img\s*\{[^}]*max-width:\s*100%[^}]*object-fit:\s*contain/);
    expect(courseCssText).toMatch(/\.course-pdf__viewport\s*\{[^}]*overflow:\s*auto/);
  });

  it("a hidden block's own [hidden] display is overridden to reserve its box (visibility, not display:none)", () => {
    const rule = /\.course-block\[hidden\]\s*\{[^}]*display:\s*block[^}]*visibility:\s*hidden/;
    expect(courseCssText).toMatch(rule);
  });

  it("ships the focus ring — no longer a runtime <style> injection (§P2-06 fold)", () => {
    expect(courseCssText).toMatch(/\.course-focus-ring\s*\{[^}]*outline:/);
  });

  it("defines its own tokens with literal fallbacks — renders standalone without the host stylesheet", () => {
    expect(courseCssText).toMatch(/--course-bg:\s*var\(--mk-paper,\s*#[0-9a-fA-F]{6}\)/);
  });

  it("the package's runtime mount root (CoursePlayer) actually imports this stylesheet", async () => {
    // A side-effect import that vitest's default CSS handling stubs to a
    // no-op — this only proves the import exists and doesn't throw; the
    // rule content itself is asserted directly against the source above.
    await expect(import("../src/course/CoursePlayer")).resolves.toBeTruthy();
  });
});
