# Rich-text teaching patterns

These examples demonstrate bounded editorial patterns. Replace all teaching content with source-backed course content and keep only the structure that serves the approved page plan.

## Example 1: a reading lens beside the original source

Use before the learner reads a substantial PDF, excerpt, image, or video. Put the card in the left side of a `1:1` split and the real source on the right. It tells the learner what to notice without summarising away the evidence or supplying the eventual answer.

```json
{
  "id": "source-reading-lens",
  "type": "richText",
  "title": "材料阅读提示",
  "html": "<style>.eyebrow{margin:0 0 6px;color:var(--course-accent);font-size:14px;font-weight:750;letter-spacing:.08em;text-transform:uppercase}.lead{color:var(--course-secondary)}.lenses{display:grid;gap:10px;margin:16px 0}.lens{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;align-items:center;padding:11px 12px;border:1px solid var(--course-border);border-radius:var(--course-radius);background:var(--course-surface)}.n{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--course-accent);color:white;font-weight:750}.lens h3,.lens p{margin:0}.lens p{margin-top:3px;color:var(--course-muted);font-size:14px}.prompt{margin-top:14px;padding:13px 14px;border-left:3px solid var(--course-accent);border-radius:0 var(--course-radius) var(--course-radius) 0;background:var(--course-accent-weak)}.prompt strong{display:block;margin-bottom:4px}</style><p class=\"eyebrow\">材料 01 · 企业主张</p><h2>这段话怎样让项目显得可靠又无害？</h2><p class=\"lead\">阅读右侧原文。先辨认反复出现的三类承诺，再判断这些承诺有没有充分证据。</p><div class=\"lenses\"><section class=\"lens\"><span class=\"n\">1</span><div><h3>经济承诺</h3><p>工作岗位、税收、旅游复苏与地方经济。</p></div></section><section class=\"lens\"><span class=\"n\">2</span><div><h3>环保承诺</h3><p>绿色空间、清洁能源与污染处理。</p></div></section><section class=\"lens\"><span class=\"n\">3</span><div><h3>生活叙事</h3><p>安全、可控、令人期待的休闲体验。</p></div></section></div><aside class=\"prompt\"><strong>阅读时抓住两件事</strong>他具体说了什么？用了哪些让人安心、期待或忽略风险的词？</aside>"
}
```

## Example 2: comparison plus worked reasoning

Use when the learner needs to see why two concepts, sources, or reasoning moves differ before practising independently.

```json
{
  "id": "comparison-model-card",
  "type": "richText",
  "title": "事实核查与立场判断的区别",
  "html": "<style>.compare{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{padding:14px;border:1px solid var(--course-border);border-radius:var(--course-radius)}.panel h3{margin:0 0 8px;color:var(--course-accent)}.model{margin-top:16px;padding:14px;background:var(--course-accent-weak);border-radius:var(--course-radius)}.label{font-size:14px;color:var(--course-muted);font-weight:700;letter-spacing:.04em}@media(max-width:680px){.compare{grid-template-columns:1fr}}</style><h2>先分清你在回答哪一个问题</h2><div class=\"compare\"><section class=\"panel\"><h3>事实核查</h3><p><strong>问题：</strong>这句话与可查证材料是否一致？</p><p><strong>需要：</strong>来源、时间、具体主张。</p></section><section class=\"panel\"><h3>立场判断</h3><p><strong>问题：</strong>你是否认同这个价值取向或政策选择？</p><p><strong>需要：</strong>标准、权衡和理由。</p></section></div><section class=\"model\"><div class=\"label\">示范推理</div><p>先核查报告是否真的使用了该数据，再讨论这种衡量方式是否合理。两个问题相关，但证据和结论不能混用。</p></section>"
}
```

## Adaptation rules

- The lens names observable dimensions and a reading purpose; it does not retell the source or reveal the later answer.
- Use short vertical rows when each dimension needs a label plus one sentence. Use columns only for genuinely parallel, compact items.
- A table works for repeated fields across several categories; two cards work better for a single contrast.
- Put one worked example after the framework, not before the learner knows what to notice.
- If the card sits beside an assessment, keep only the reference needed for that assessment and place the answerable Block in the right slot.
