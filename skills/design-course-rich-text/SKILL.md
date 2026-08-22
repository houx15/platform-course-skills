---
name: design-course-rich-text
description: Use when an approved course page needs a static richText Block to present a methodology, worked example, comparison, reference table, definition set, or synthesis more clearly than Markdown, without learner interaction.
---

# Design Course Rich Text

Turn already-approved teaching content into one safe, readable `richText` Block. This is an internal production specialist: preserve the page plan, method step, source meaning, terminology, and learner-state change. Improve editorial structure and visual hierarchy; do not invent a new methodology, example, claim, question, or assessment.

## When to use it

Use `richText` when visual structure carries instructional meaning, especially:

- a course overview that turns the approved learning arc into a learner-visible route through methods, cases and the final cumulative result;
- a method-position card that shows the current method, active step, reason for the exercise, and the next step;
- a methodology with ordered steps, purposes, and common mistakes;
- a reading lens beside a source: state why the learner is reading, name the dimensions to notice, and end with the question they should carry into the source;
- a worked example that separates observation, reasoning, and conclusion;
- a two-way comparison, evidence ladder, source taxonomy, rubric, or decision table;
- a definition set, annotated checklist, synthesis map, or compact reference card;
- a static knowledge diagram whose flow, hierarchy, causal chain, matrix, or relationship map makes the concept easier to understand;
- an explanation whose callouts, grouping, labels, or hierarchy would be flattened by Markdown.

Keep `text` for short prose. Use `images`, `pdf`, or `video` for real media. Use `interactiveHtml`, `fillBlank`, or `singleChoice` whenever the learner must act or submit evidence. A `richText` Block is display-only and never completes a Slice.

## Authoring workflow

1. Read the approved teaching design, page-plan row, source bindings, and the Slice's neighbouring Blocks. Identify the one teaching job the card performs and the method step or learner-state change it supports.
2. Choose the smallest editorial structure that makes that job easier to understand. Do not add panels merely to make the screen look decorated.
   When the card prepares a source reading, keep the actual PDF, image, or excerpt in its own Block. The card should orient attention instead of replacing the source with a summary.
   When the card supports an exercise, make the causal sequence visible before the prompt: what the learner already established, which method step is active, why this practice is needed now, and what the result unlocks next.
3. Write a self-contained HTML fragment in the Block's `html` field. Inline one `<style>` block when needed. Use semantic headings, lists, tables, `blockquote`, `dl`, and labelled sections before adding generic containers. Static HTML/CSS diagrams may use labelled cards, connectors, grids and rails to show a flow, hierarchy, causal chain, matrix or relationship map. Keep a logical reading order so the structure remains understandable without the diagram styling.
4. Prefer `--course-ink`, `--course-secondary`, `--course-muted`, `--course-surface`, `--course-border`, `--course-accent`, `--course-accent-weak`, and `--course-radius`. Keep body text at least `15px`, secondary text at least `14px`, and use readable line lengths and spacing. A restrained card still needs real editorial structure: combine at least two clearly styled teaching regions. Suitable primitives include a hint/callout, large numbered steps, two or three subtle card tones derived with `color-mix()`, a progress rail, a labelled comparison, or a worked-example panel. Do not create a rainbow dashboard, decorative icon cloud, or a plain heading-plus-list that merely happens to sit inside an iframe.
5. Keep the fragment within 64 KB. If the learner must scroll through several distinct ideas, split the teaching sequence into separate Slices rather than building one long card.
6. Insert the Block into `.course-work/course-blueprint.json`, assign it to a tall slot (`full` or one side of `split-horizontal`), then compile and inspect it in the offline preview that uses the pinned student renderer. Never edit generated `course/course.json` directly.

## Hard boundaries

- No `<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<link>`, `<base>`, inline `on...=` handlers, or `javascript:` URLs.
- No external stylesheets, webfonts, remote images, or relative asset paths. Use an `images` Block for course images; only very small decorative images may be inlined as data URIs.
- Do not simulate buttons, inputs, tabs, accordions, drag targets, or other affordances. If it looks actionable, it must actually be an interactive Block.
- Do not hard-code a separate brand palette. Use the course variables so the card follows the student's chosen accent.
- Do not encode crucial meaning through colour alone. Retain visible labels and logical reading order.
- Do not copy planning notes, source IDs, AI rationale, or answer keys into learner-facing HTML.
- Avoid formulaic `不是……而是……` / `not X but Y` contrast in learner-facing copy. State the concept, action and causal relationship directly. Keep a contrast only when the approved teaching content genuinely distinguishes two concepts.

## Quality check

Before returning the Block, verify:

- every visible claim is already supported by the approved sources or teaching design;
- the first screen makes the card's purpose and hierarchy apparent;
- a full-screen course overview makes the learning route, cases and intended result visible rather than leaving most of the page empty;
- an exercise-support card states the active method step, why this exercise follows now and what it prepares next before the learner sees the question;
- a reading-lens card names the source-reading purpose, observable dimensions, and a concrete question without revealing the answer;
- the HTML contains an inline style and at least two semantically meaningful, visibly differentiated regions; otherwise use `text` or redesign the card;
- the layout improves comprehension of the method, example, or comparison;
- a knowledge diagram expresses a real relationship and remains readable in semantic document order; it is never added as decoration;
- the card remains understandable without its colours;
- there is no interaction or completion expectation;
- the shared validator accepts it and the real offline renderer shows no clipping, unreadable text, or unnecessary internal scrolling.

Read [examples.md](references/examples.md) when writing a reading-lens/method card or a comparison/worked-example card. Adapt their structure, not their subject matter or wording.
