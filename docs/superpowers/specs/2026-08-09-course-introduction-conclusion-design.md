# Course Introduction and Conclusion Design

日期：2026-08-09

## 1. 目标

每门标准课程必须形成完整的学生学习闭环：学习开始前有独立的课程介绍页，全部必修内容完成后有结课报告中的课程总结。老师可以直接提供课程目标、课程总结和学生收获；材料缺失时，AI 根据课程证据提出面向学生的草案，并让老师一次确认。

开场页和结课总结属于课程级语义，不伪装成普通 Part、Piece 或 Block。它们不会影响 Part/Piece 数量，也不使用 Block 的阻塞与完成规则。

## 2. 方案选择

采用 `course.introduction` 和 `course.conclusion` 两个必需的顶层结构化对象。

不采用以下方案：

- 特殊 introduction/conclusion Block：会混淆课程级页面与 Piece 内的教学内容、完成规则和模态 Review；
- 固定首尾 Part：会污染 Part/Piece 统计，允许 AI 或老师把它们错误排序，并让课程总结看起来像普通学习阶段。

平台固定渲染第一幕和结课报告；`index.md` 以确定性 Markdown 表达同一学生视图。

## 3. Schema 版本

本次合同升级为 `schemaVersion: "1.1"`，因为开场与结尾从不存在变为每门课程必需，属于破坏性合同变化。

- Builder 只生成 `1.1` 课程；
- validator 能识别旧 `1.0` 课程，并返回 `migration-required`；
- 旧课程不能直接返回 `可上传`；
- AI 读取旧课程的实际 Part、Piece、Block 和工作记录，起草首尾内容并让老师确认后升级；
- 不静默生成通用套话，不要求老师直接编辑 JSON。

## 4. 课程数据合同

```json
{
  "schemaVersion": "1.1",
  "course": {
    "id": "evidence-comparability",
    "title": "相互矛盾的证据，真的可以直接比较吗？",
    "language": "zh-CN",
    "introduction": {
      "overview": "面对看起来互相矛盾的观点，本课不会要求你立即选边。你将先检查这些证据是否在讨论同一个对象、使用相同的数据结构、研究范围和测量方法。",
      "objectives": [
        {
          "id": "check-comparability",
          "text": "面对相互矛盾的证据时，先检查它们是否具备直接比较的条件"
        }
      ],
      "keyPoints": [
        "比较对象是否相同",
        "数据构成是否一致",
        "研究范围与尺度是否可比",
        "数字产生方式是否一致"
      ]
    },
    "parts": [
      {
        "id": "compare-evidence",
        "title": "检查证据能否直接比较",
        "pieces": [
          {
            "id": "comparability-practice",
            "title": "完成一次可比性检查",
            "blocks": [
              {
                "id": "comparability-check-response",
                "type": "fillBlank",
                "blocking": true,
                "prompt": "面对两条相互矛盾的结论，你会先检查什么？",
                "assessment": {
                  "mode": "reflection",
                  "rubric": "回答应至少检查研究对象、数据构成、范围尺度或数字产生方式中的一项。"
                }
              }
            ]
          }
        ]
      }
    ],
    "conclusion": {
      "summary": "本课从一个表面冲突出发，逐步拆解两条证据背后的研究对象、数据结构、范围尺度和测量方法。很多看似互相矛盾的结论，实际上可能没有回答同一个问题。",
      "takeaways": [
        "方向相反的结论不一定构成真正冲突",
        "只有边界与方法可比的证据，才适合直接比较",
        "判断前先检查可比性，可以避免过早选边"
      ],
      "transferApplications": [
        "论文阅读",
        "新闻比较",
        "AI 答案核查"
      ]
    }
  }
}
```

### 4.1 `introduction`

必需字段：

- `overview`：非空、面向学生的课程介绍；
- `objectives`：1–5 个目标对象；
- `objectives[].id`：小写连字符 ID，加入全课程唯一 ID 检查；
- `objectives[].text`：非空、学生可以理解的目标表达；
- `keyPoints`：2–6 条非空关键点。

目标应表达学生要形成的判断、行动或能力。仅写“了解本课内容”“学习相关知识”“掌握有关概念”不能通过语义 Review。

### 4.2 `conclusion`

必需字段：

- `summary`：非空、面向学生的课程总结；
- `takeaways`：2–6 条非空 takeaway；
- `transferApplications`：1–8 个非空迁移场景。

总结只能回顾课程实际教授、练习或验证过的内容。它不能引入新知识、把完成课程等同于掌握能力，或声称平台没有证据支持的学习效果。

### 4.3 明确禁止的字段

`introduction` 和 `conclusion` 不允许：

- `blocking`；
- `completion`；
- `startButtonLabel`；
- 平台实现、教师说明、AI 规则或 source coverage 字段。

“开始学习”是平台固定行为，不需要每门课重复配置，也不进入课程 JSON。

## 5. 平台与 `index.md` 呈现

### 5.1 第一幕

平台在第一个 Part 之前显示：

1. `course.title`；
2. `introduction.overview`；
3. “你将学会”目标列表；
4. “学习关键点”列表；
5. 固定“开始学习”按钮。

按钮不产生 Block 完成记录；点击后进入第一个 Part。

生成的 `index.md` 使用：

```markdown
# 相互矛盾的证据，真的可以直接比较吗？

[课程开始页]

## 课程介绍

面对看起来互相矛盾的观点……

## 你将学会

- 面对相互矛盾的证据时，先检查它们是否具备直接比较的条件

## 学习关键点

- 比较对象是否相同
- 数据构成是否一致

[开始学习]
```

`[开始学习]` 是生成视图中的固定平台行为标记，不来自 JSON 可编辑字段。

### 5.2 结课报告

全部必修课程内容完成后，平台结课报告组合：

- 动态数据：真实完成情况、题目结果和交互记录；
- 静态课程内容：`conclusion.summary`、`takeaways`、`transferApplications`。

`index.md` 在所有 Part 后生成：

```markdown
[结课报告内容]

## 课程总结

本课从一个表面冲突出发……

## 你可以带走什么

- 方向相反的结论不一定构成真正冲突

## 你可以在哪里使用

- 论文阅读
- 新闻比较
- AI 答案核查
```

课程 JSON 不保存学生动态成绩或完成结果。静态结论不根据答题结果自动改写。

## 6. 材料分析与老师确认

材料分析识别以下来源意图：

- 课程目标；
- 课程介绍、背景或学习缘由；
- 课程总结；
- 学生收获；
- 迁移应用。

这些内容先作为高价值来源证据保存。AI 不直接复制老师提供的长段落，而是结合实际 Part、Piece、活动和评价整理为学生可读的概述、目标、关键点、总结、takeaway 和迁移场景。

当老师没有提供完整内容时：

1. 能从已确认材料可靠推出的内容，由 AI 给出明确草案；
2. 会改变课程目的、学科结论或学习效果声明的缺口，进入待确认；
3. 不逐字段询问老师，而是在同一张表中批量确认。

## 7. Storyboard 与确认表

现有 Part/Piece 表之前，展示课程首尾设计表：

| 区域 | 学生最终会看到的内容 | 来源与判断依据 | 待确认 |
| --- | --- | --- | --- |
| 开场介绍 | 学生可读 overview | source ID 或 AI 归纳说明 | 状态 |
| 课程目标 | 1–5 条目标 | 原始目标、活动与评价 | 状态 |
| 学习关键点 | 2–6 条关键点 | Part 教学重点 | 状态 |
| 结课总结 | 对实际学习过程的总结 | 已设计 Part/Piece | 状态 |
| 学生带走什么 | 2–6 条 takeaway | 目标与评价 | 状态 |
| 可以迁移到哪里 | 1–8 个场景 | 材料或合理归纳 | 状态 |

老师一次确认课程首尾表和 Part/Piece 表。任何实质性修改都更新 JSON 并重新生成表格。

`.course-work/course-storyboard.json` 增加：

```json
{
  "courseFrame": {
    "teacherConfirmed": true,
    "sourceIds": ["source-12", "source-18"],
    "objectiveAlignment": [
      {
        "objectiveId": "check-comparability",
        "partIds": ["compare-evidence"],
        "evidenceBlockIds": [
          "comparability-check-response"
        ]
      }
    ],
    "pendingConfirmations": []
  }
}
```

每个目标至少映射到一个真实 Part，以及至少一个真实学习证据 Block。缺少目标证据时，AI 必须补充合适的评价活动或与老师确认调整目标；不能仅用“学生已经阅读”代替学习证据。

## 8. Skills 行为

### `analyze-course-materials`

- 识别目标、总结、学生收获和迁移表达；
- 保留来源 ID 和原位置；
- 区分老师的教学意图与学生最终措辞；
- 缺失时报告可推断内容和真正需要确认的缺口。

### `build-platform-course`

- 在设计 Part/Piece 后，根据完整学习路径整理首尾内容；
- 展示课程首尾表和 Part/Piece 表，获得一次完整确认；
- 生成 `1.1` `course.json`；
- 不把开场或结尾伪装成 Part/Piece；
- 不在按钮、总结或学生收获中写入无证据的完成/掌握声明。

### `review-platform-course`

- 逐项对照首尾确认表、目标对齐、课程内容和评价证据；
- Review 表固定增加 `courseIntroduction`、`courseConclusion`；
- 旧 `1.0` 课程返回阻塞迁移结果；
- 任一首尾语义问题阻止 `可上传`。

HTML、视频和 PDF 设计 Skills 不改变。

## 9. Review 规则

### 9.1 `courseIntroduction`

检查：

- overview、目标、关键点完整；
- 直接面向学生，表达清楚且不过度冗长；
- 每个目标与真实 Part 和学习证据对齐；
- 开场没有承诺课程未教授或未评价的内容；
- 没有教师设计、AI 规则、后台字段或 source coverage 泄漏。

### 9.2 `courseConclusion`

检查：

- summary 回顾实际学习路径；
- takeaway 可由课程内容与活动支持；
- 迁移场景与所学能力相符；
- 没有新引入的学科结论；
- 没有把完成记录写成已经理解或掌握；
- 没有原样复制老师长文造成学生呈现冗长。

以上任一失败使整体 Review 为 `revise`，阻止上传。

## 10. 旧课程迁移

遇到 `1.0` 课程时：

1. 保留原始文件；
2. 重新读取课程标题、Part/Piece、活动、评价及 `.course-work`；
3. 提取或起草 introduction/conclusion；
4. 建立 objective alignment；
5. 展示课程首尾确认表；
6. 老师确认后写入 `1.1` 并重新生成 `index.md`；
7. 重新运行完整 Review。

未确认的迁移不得上传，也不得以机械格式修复标记为“修改后可上传”。

## 11. 自动测试与样例

新增测试覆盖：

- 合法 `1.1` 课程；
- 缺少 introduction 或 conclusion；
- 空目标、重复目标 ID、目标数量越界；
- 关键点、takeaway、迁移场景数量边界；
- 禁止的额外字段；
- `index.md` 首屏、固定按钮标记和结课报告顺序；
- 旧 `1.0` 的 `migration-required`；
- courseFrame 老师确认；
- objective 到 Part/evidence Block 的真实 ID 对账；
- Review 缺少 `courseIntroduction` 或 `courseConclusion`；
- Skill 场景覆盖老师提供/未提供目标与总结两种情况；
- tracked valid fixture 升级到 `1.1`；
- 本地 `format/example_output` 升级并继续返回 `可上传`。

## 12. 验证边界

工具可以验证结构、首尾内容存在、来源和目标对齐记录、生成视图一致，以及 Review 是否完整。它不能仅凭课程完成情况证明学生真正理解、掌握或迁移了课程能力。结课报告必须将平台事实、课程静态总结和学习效果推断保持分离。
