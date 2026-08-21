# Rich-text teaching patterns

These examples demonstrate bounded editorial patterns. Replace all teaching content with source-backed course content and keep only the structure that serves the approved page plan.

## Example 1: methodology steps with a mistake callout

Use after the method has been introduced or when the learner needs one stable reference while following a model.

```json
{
  "id": "method-steps-card",
  "type": "richText",
  "title": "三步核查法",
  "html": "<style>.steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.step{border:1px solid var(--course-border);border-radius:var(--course-radius);padding:14px}.n{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--course-accent);color:white;font-weight:700}.step h3{margin:.6em 0 .3em}.mistake{margin-top:14px;padding:12px 14px;border-left:3px solid var(--course-accent);background:var(--course-accent-weak)}@media(max-width:680px){.steps{grid-template-columns:1fr}}</style><h2>三步核查法</h2><p>先确定主张，再寻找来源，最后判断证据能支持到哪一步。</p><div class=\"steps\"><section class=\"step\"><span class=\"n\">1</span><h3>圈出主张</h3><p>写清谁在什么情境下声称了什么。</p></section><section class=\"step\"><span class=\"n\">2</span><h3>找到来源</h3><p>区分原始材料、转述和评论。</p></section><section class=\"step\"><span class=\"n\">3</span><h3>限定结论</h3><p>只说证据实际支持的范围。</p></section></div><aside class=\"mistake\"><strong>常见错误</strong><br>把“有人提出质疑”直接写成“已经证明结论错误”。</aside>"
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

- Three columns work for short, parallel steps; use a vertical sequence when each step needs substantial explanation.
- A table works for repeated fields across several categories; two cards work better for a single contrast.
- Put one worked example after the framework, not before the learner knows what to notice.
- If the card must sit beside an assessment, keep only the reference needed to answer that assessment and place the answerable Block in the right slot.
