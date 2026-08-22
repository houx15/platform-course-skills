# Rich-text teaching patterns

These examples demonstrate bounded editorial patterns. Replace all teaching content with source-backed course content and keep only the structure that serves the approved page plan.

## Example 1: course overview as a visible learning route

Use when a complex course benefits from a visible route at the opening. This is one introduction pattern, not a mandatory first-Slice template: a story, case conflict, observation, demonstration, or problem situation may be a better entry. The card is restrained: large numbered method cards, one case strip and one outcome hint rather than a decorative dashboard.

```json
{
  "id": "course-route-overview",
  "type": "richText",
  "title": "本课学习路线",
  "html": "<style>.eyebrow{margin:0;color:var(--course-accent);font-size:13px;font-weight:750;letter-spacing:.08em}.lead{max-width:62ch;color:var(--course-secondary);font-size:16px}.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:22px 0}.step{min-height:150px;padding:16px;border:1px solid var(--course-border);border-radius:var(--course-radius);background:var(--course-surface)}.step:nth-child(2){background:color-mix(in srgb,var(--course-accent-weak) 55%,var(--course-surface))}.step:nth-child(3){background:color-mix(in srgb,var(--course-accent) 7%,var(--course-surface))}.n{display:block;margin-bottom:14px;color:var(--course-accent);font-size:34px;font-weight:800;line-height:1}.step h3,.step p{margin:0}.step p{margin-top:8px;color:var(--course-muted);font-size:14px}.case{display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:center;padding:14px 16px;border-block:1px solid var(--course-border)}.case strong{color:var(--course-accent)}.outcome{margin-top:18px;padding:14px 16px;border-left:4px solid var(--course-accent);border-radius:0 var(--course-radius) var(--course-radius) 0;background:var(--course-accent-weak)}@media(max-width:760px){.route{grid-template-columns:1fr}.step{min-height:0}}</style><p class=\"eyebrow\">今天的学习路线</p><h2>把“像漂绿”变成一条可复核的判断</h2><p class=\"lead\">我们会学习三个连续动作，并把它们带入企业传播案例。每一步都会留下证据，最后组成一份核查记录。</p><div class=\"route\"><section class=\"step\"><span class=\"n\">01</span><h3>拆主张</h3><p>把宽泛表述改写成可以查证的事实问题。</p></section><section class=\"step\"><span class=\"n\">02</span><h3>分证据</h3><p>区分承诺、行动、结果与仍然未知的部分。</p></section><section class=\"step\"><span class=\"n\">03</span><h3>校语言</h3><p>只写证据真正支持的结论和边界。</p></section></div><section class=\"case\"><strong>会看的案例</strong><span>企业 ESG 截图、评级材料与一组公开传播页面。</span></section><aside class=\"outcome\"><strong>最后你会完成：</strong>一份包含主张、来源、证据层级和下一步核查方向的判断记录。</aside>"
}
```

## Example 2: method position before a guided exercise

Use on the left of a `1:1` split, with the source and answer surface on the right or in the next clearly connected region. It shows why the exercise exists instead of dropping the learner into a question.

```json
{
  "id": "method-position-card",
  "type": "richText",
  "title": "当前练习位置",
  "html": "<style>.position{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:12px;border-bottom:1px solid var(--course-border)}.badge{padding:5px 10px;border-radius:999px;background:var(--course-accent-weak);color:var(--course-accent);font-size:13px;font-weight:750}.rail{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:18px 0}.rail span{height:7px;border-radius:999px;background:var(--course-border)}.rail .done{background:color-mix(in srgb,var(--course-accent) 45%,var(--course-border))}.rail .active{background:var(--course-accent)}.focus{padding:16px;border:1px solid var(--course-border);border-radius:var(--course-radius);background:var(--course-surface)}.focus h3{margin:0 0 8px}.focus p{margin:0;color:var(--course-secondary)}.why{margin-top:14px;padding:13px 14px;border-left:3px solid var(--course-accent);background:var(--course-accent-weak);border-radius:0 var(--course-radius) var(--course-radius) 0}.next{margin-top:14px;color:var(--course-muted);font-size:14px}</style><div class=\"position\"><div><small>方法一 · 主张拆解</small><h2>第 2 步：变成可核查问题</h2></div><span class=\"badge\">带练</span></div><div class=\"rail\" aria-label=\"三步中的第二步\"><span class=\"done\"></span><span class=\"active\"></span><span></span></div><section class=\"focus\"><h3>这一页只练一件事</h3><p>从截图中选出一条具体表述，把“它靠谱吗”改写成包含对象、时间和结果的核查问题。</p></section><aside class=\"why\"><strong>为什么现在做？</strong><br>上一页已经区分了事实主张和价值判断；只有先写清要核查的事实，下一步才知道应该找什么来源。</aside><p class=\"next\">完成后：带着你的问题进入来源选择。</p>"
}
```

## Example 3: a reading lens beside the original source

Use before the learner reads a substantial PDF, excerpt, image, or video. Put the card in the left side of a `1:1` split and the real source on the right. It tells the learner what to notice without summarising away the evidence or supplying the eventual answer.

```json
{
  "id": "source-reading-lens",
  "type": "richText",
  "title": "材料阅读提示",
  "html": "<style>.eyebrow{margin:0 0 6px;color:var(--course-accent);font-size:14px;font-weight:750;letter-spacing:.08em;text-transform:uppercase}.lead{color:var(--course-secondary)}.lenses{display:grid;gap:10px;margin:16px 0}.lens{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;align-items:center;padding:11px 12px;border:1px solid var(--course-border);border-radius:var(--course-radius);background:var(--course-surface)}.n{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--course-accent);color:white;font-weight:750}.lens h3,.lens p{margin:0}.lens p{margin-top:3px;color:var(--course-muted);font-size:14px}.prompt{margin-top:14px;padding:13px 14px;border-left:3px solid var(--course-accent);border-radius:0 var(--course-radius) var(--course-radius) 0;background:var(--course-accent-weak)}.prompt strong{display:block;margin-bottom:4px}</style><p class=\"eyebrow\">材料 01 · 企业主张</p><h2>这段话怎样让项目显得可靠又无害？</h2><p class=\"lead\">阅读右侧原文。先辨认反复出现的三类承诺，再判断这些承诺有没有充分证据。</p><div class=\"lenses\"><section class=\"lens\"><span class=\"n\">1</span><div><h3>经济承诺</h3><p>工作岗位、税收、旅游复苏与地方经济。</p></div></section><section class=\"lens\"><span class=\"n\">2</span><div><h3>环保承诺</h3><p>绿色空间、清洁能源与污染处理。</p></div></section><section class=\"lens\"><span class=\"n\">3</span><div><h3>生活叙事</h3><p>安全、可控、令人期待的休闲体验。</p></div></section></div><aside class=\"prompt\"><strong>阅读时抓住两件事</strong>他具体说了什么？用了哪些让人安心、期待或忽略风险的词？</aside>"
}
```

## Example 4: comparison plus worked reasoning

Use when the learner needs to see why two concepts, sources, or reasoning moves differ before practising independently.

```json
{
  "id": "comparison-model-card",
  "type": "richText",
  "title": "事实核查与立场判断的区别",
  "html": "<style>.compare{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{padding:14px;border:1px solid var(--course-border);border-radius:var(--course-radius)}.panel h3{margin:0 0 8px;color:var(--course-accent)}.model{margin-top:16px;padding:14px;background:var(--course-accent-weak);border-radius:var(--course-radius)}.label{font-size:14px;color:var(--course-muted);font-weight:700;letter-spacing:.04em}@media(max-width:680px){.compare{grid-template-columns:1fr}}</style><h2>先分清你在回答哪一个问题</h2><div class=\"compare\"><section class=\"panel\"><h3>事实核查</h3><p><strong>问题：</strong>这句话与可查证材料是否一致？</p><p><strong>需要：</strong>来源、时间、具体主张。</p></section><section class=\"panel\"><h3>立场判断</h3><p><strong>问题：</strong>你是否认同这个价值取向或政策选择？</p><p><strong>需要：</strong>标准、权衡和理由。</p></section></div><section class=\"model\"><div class=\"label\">示范推理</div><p>先核查报告是否真的使用了该数据，再讨论这种衡量方式是否合理。两个问题相关，但证据和结论不能混用。</p></section>"
}
```

## Example 5: knowledge structure as a static diagram

Use when the relationship between concepts is itself the teaching content. This example uses semantic sections in document order and CSS connectors to reveal a causal chain. The labels still make sense if the connectors or colours disappear.

```json
{
  "id": "evidence-chain-diagram",
  "type": "richText",
  "title": "证据如何支持判断",
  "html": "<style>.lead{max-width:62ch;color:var(--course-secondary)}.chain{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:30px;margin:24px 0}.node{position:relative;min-height:170px;padding:17px;border:1px solid var(--course-border);border-radius:var(--course-radius);background:var(--course-surface)}.node:nth-child(2){background:color-mix(in srgb,var(--course-accent-weak) 55%,var(--course-surface))}.node:not(:last-child)::after{content:'→';position:absolute;right:-23px;top:50%;color:var(--course-accent);font-size:26px;font-weight:800;transform:translateY(-50%)}.tag{display:inline-block;margin-bottom:16px;color:var(--course-accent);font-size:13px;font-weight:800;letter-spacing:.06em}.node h3,.node p{margin:0}.node p{margin-top:8px;color:var(--course-muted);font-size:14px}.check{padding:14px 16px;border-left:4px solid var(--course-accent);border-radius:0 var(--course-radius) var(--course-radius) 0;background:var(--course-accent-weak)}@media(max-width:760px){.chain{grid-template-columns:1fr;gap:12px}.node{min-height:0}.node:not(:last-child)::after{display:none}}</style><h2>一条可靠判断怎样形成？</h2><p class=\"lead\">三类信息依次连接。任何一环缺失，结论都要保留边界。</p><div class=\"chain\" aria-label=\"从主张到证据再到判断的三步关系\"><section class=\"node\"><span class=\"tag\">01 · 主张</span><h3>具体说了什么</h3><p>对象、时间、行动与结果能够被单独核查。</p></section><section class=\"node\"><span class=\"tag\">02 · 证据</span><h3>材料实际支持什么</h3><p>来源、口径和时间范围决定证据的覆盖边界。</p></section><section class=\"node\"><span class=\"tag\">03 · 判断</span><h3>写出支持程度</h3><p>分别说明可确认、可推断和仍需核查的部分。</p></section></div><aside class=\"check\"><strong>本页检查点：</strong>你的判断能否沿着这条链回到具体证据？</aside>"
}
```

## Adaptation rules

- The course has a meaningful introduction before the first demand. If that introduction is an overview, it makes method, cases and final result visible.
- A practice page includes a method-position surface before the question; a hidden method ID is not enough.
- The lens names observable dimensions and a reading purpose; it does not retell the source or reveal the later answer.
- Use short vertical rows when each dimension needs a label plus one sentence. Use columns only for genuinely parallel, compact items.
- A table works for repeated fields across several categories; two cards work better for a single contrast.
- A static diagram earns its space only when flow, hierarchy, causality, a matrix, or relationships are easier to understand visually. Preserve semantic reading order and visible labels.
- Put one worked example after the framework, not before the learner knows what to notice.
- If the card sits beside an assessment, keep only the reference needed for that assessment and place the answerable Block in the right slot.
