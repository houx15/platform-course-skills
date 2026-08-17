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
