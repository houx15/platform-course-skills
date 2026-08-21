import { describe, it, expect } from "vitest";
import { BlockDefinition, RICH_TEXT_MAX_CHARS } from "../src/blocks";

const card = {
  id: "definition-card",
  type: "richText",
  html: `<style>.k{color:#b0463a}</style><h2>三种“来源”</h2><table><tr><th>类型</th><th>看什么</th></tr><tr><td class="k">原始发布</td><td>时间、账号、上下文</td></tr></table>`,
};

describe("RichTextBlock", () => {
  it("parses an authored card, inline <style> included — styling IS the feature", () => {
    expect(BlockDefinition.safeParse(card).success).toBe(true);
  });

  it("accepts an optional accessible title and rejects unknown properties (strict)", () => {
    expect(BlockDefinition.safeParse({ ...card, title: "来源类型对照" }).success).toBe(true);
    expect(BlockDefinition.safeParse({ ...card, source: "x.html" }).success).toBe(false);
  });

  it("carries no completion rule — a display card can never complete a Slice", () => {
    expect(BlockDefinition.safeParse({ ...card, completion: { rule: "interaction-complete" } }).success).toBe(false);
  });

  it("rejects empty html", () => {
    expect(BlockDefinition.safeParse({ ...card, html: "" }).success).toBe(false);
  });

  it.each([
    ["<script>", `<p>hi</p><script>alert(1)</script>`],
    ["a spaced script tag", `< script >alert(1)</script>`],
    ["an iframe", `<iframe src="https://evil.example"></iframe>`],
    ["an object", `<object data="x"></object>`],
    ["a form", `<form action="/steal"><input name="p"></form>`],
    ["an external stylesheet", `<link rel="stylesheet" href="https://cdn.example/x.css">`],
    ["a base tag", `<base href="https://evil.example/">`],
    ["an inline event handler", `<div onclick="steal()">tap</div>`],
    ["a javascript: URL", `<a href="javascript:alert(1)">go</a>`],
  ])("rejects %s", (_label, html) => {
    const result = BlockDefinition.safeParse({ ...card, html });
    expect(result.success).toBe(false);
  });

  it("explains what to do instead, so the rejection is actionable", () => {
    const result = BlockDefinition.safeParse({ ...card, html: `<form></form>` });
    expect(result.success).toBe(false);
    if (result.success) return;
    expect(result.error.issues.map((i) => i.message).join(" ")).toContain("fillBlank/singleChoice");
  });

  it("does not mistake ESCAPED markup in prose for real markup", () => {
    // A card explaining what a script tag is must still validate.
    const html = `<p>攻击者会插入 &lt;script&gt; 标签。</p>`;
    expect(BlockDefinition.safeParse({ ...card, html }).success).toBe(true);
  });

  it("caps the authored html so a definition document stays sane", () => {
    const tooBig = "<p>" + "字".repeat(RICH_TEXT_MAX_CHARS) + "</p>";
    expect(BlockDefinition.safeParse({ ...card, html: tooBig }).success).toBe(false);
  });
});
