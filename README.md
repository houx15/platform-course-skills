# 平台课程标准化工具包

这套 Skills 帮助教师把已有的 Word、HTML、Markdown、文本、PDF 及其他课程材料逐步整理为平台可处理、可追溯、可检查的标准课程。

## 一句话安装

老师只需要在 Codex 中发送：

```text
帮我安装这套 Skills：https://github.com/houx15/platform-course-skills
```

安装完成后的下一轮对话，老师就可以发送：

```text
使用 $build-platform-course，把我的已有材料整理成可上传的平台课程。
```

### Codex 安装协议

以下内容供收到上述请求的 AI 执行。不要要求老师自己打开终端、选择 Skill 或补充安装命令。

1. 这是包含 5 个课程 Skills 和共用运行时的工具包。不要把仓库根目录当作单个 Skill，也不要只安装其中一个子目录。
2. 使用用户提供的 HTTPS 仓库地址，将仓库克隆到临时目录或其他不会覆盖用户课程材料的位置。
3. 在克隆后的仓库根目录运行：

   ```bash
   python3 scripts/install-skills.py --target codex
   ```

4. 确认 `~/.codex/skills/` 中存在以下目录：
   - `build-platform-course`
   - `analyze-course-materials`
   - `design-course-html`
   - `design-video-interactions`
   - `review-platform-course`
   - `_course-toolkit`
5. 如果目标目录已经存在，不要删除其他 Skills。首次安装请求应说明已存在；只有用户明确要求更新时才增加 `--replace`。
6. 安装成功后告诉用户这些 Skills 将在下一轮对话可用，并给出 `$build-platform-course` 的启动示例。不要在安装请求中擅自开始构建课程。

## 手动安装

要求 Python 3.9 或更高版本。

```bash
git clone https://github.com/houx15/platform-course-skills.git
cd platform-course-skills
python3 scripts/install-skills.py --target codex
```

同时安装到 Codex 和 Claude Code：

```bash
python3 scripts/install-skills.py --target both
```

只安装一端：

```bash
python3 scripts/install-skills.py --target codex
python3 scripts/install-skills.py --target claude
```

默认使用独立副本，不依赖本工具包继续留在原位置。重新安装已有版本时显式增加 `--replace`。

更新已经安装的 Skills：

```bash
git pull
python3 scripts/install-skills.py --target both --replace
```

## 教师使用

教师进入自己的材料仓库后，只需调用主入口：

Codex：

```text
使用 $build-platform-course，把这些已有材料整理成可上传的平台课程。
```

Claude Code：

```text
/build-platform-course 把这些已有材料整理成可上传的平台课程。
```

然后提供需要处理的文件或目录。AI 会先提取材料并区分学生内容、教师设计、AI/系统规则、参考资料和拟排除内容；即使原文没有提到，也会明确询问是否需要长视频或 HTML 交互。遇到论文原文、完整报告或政策文件时，AI 会确认该 PDF 是仅用于分析，还是需要作为完整材料呈现给学生。

生成课程之前，AI 会先给出课程首尾设计表，把老师提供或补充确认的课程目标、课程总结和学生收获整理成学生适合阅读的介绍、要点与迁移场景；随后给出完整的 Part/Piece 设计表。第二张表会说明总共有多少 Part 和 Piece，并且一行对应一个 Piece，列出学生看到什么、教学重点、呈现方式、学生行动、完成标准以及资源或待确认项。老师一次确认两张表后才进入生成。AI 不会默认把每段材料变成 text block；如果认为需要流程图、示意图或信息图，只会先提出建议，得到老师明确同意后才生成。

每门课程的第一幕是独立课程介绍页，展示课程简介、课程目标和学习关键点，并由平台提供固定的“开始学习”按钮；它不计入 Part/Piece。全部 Part 完成后，结课报告展示课程总结、学生应带走的要点和可迁移场景。静态课程总结不会声称某位学生已经掌握内容。

最终交付位于 `course/`；过程记录位于 `.course-work/`。只上传 `course/`，不需要 ZIP。课程可以使用原生 `pdf` Block，将老师确认的原始文件放在 `assets/pdfs/`，供平台内嵌阅读和下载；第一版不追踪学生是否读完。

视频必须使用 MP4 封装、H.264 视频编码、AAC 音频编码（无音轨的视频可以不含 AAC），并开启 faststart。不符合或无法验证时，课程会显示“缺少必要材料，暂不可上传”。AI 会建议老师在新会话中用不会覆盖原文件的 `ffmpeg -n` 命令生成新副本；只有老师明确授权，当前会话才可以把转换交给 subagent。视频超过 10 分钟时会提醒检查是否需要增加有教学意义的交互点；文件超过 500 MiB 时会提醒确认平台上传限制，这两项提醒本身不阻止上传。

HTML 的正文和控件字号不得低于 16px；只有明确标记的辅助文字可以使用 14px，任何可见文字都不得低于 14px。每个 HTML Block 都会在 `.course-work/html-reports/` 生成 JSON 与 Markdown 检查报告。完整 Review 会核对文件摘要与当前 HTML 是否一致；报告缺失或过期会阻止上传。静态报告通过后，仍需在真实平台 iframe 中检查显示、操作和完成消息。

course.json 和 index.md 只包含学生最终会看到的内容；教学设计、教师说明、AI 规则、平台实现和 source coverage 都留在 `.course-work/`。

完成真实学生端预览与独立终审后，AI 会先生成发布 dry run：明确这是创建还是更新同一门远端课程、哪些素材按哈希上传或复用、预期远端 revision、发布状态与可见性。老师批准的是这份精确计划；课程、素材、终审证据、远端发现结果或发布选项变化后必须重新批准。当前仓库已经实现本地素材清单、稳定课程身份、发布预检和 mock adapter 幂等/恢复测试，但没有真实 OSS 或学生端课程接口适配器，也没有教师可调用的真实发布命令。本地完成不会上传、POST 或标记课程已发布。

Review 会先输出 Part 逐项 Review 表，分别检查每个 Part 的教学目标与结构、内容完整性、学生呈现、模态选择、练习与反馈、资源与格式；任一维度失败，该 Part 与整门课都不能判为可上传。随后输出整体 Review 表，检查所有 Part、来源分类与覆盖、资源、JSON、index、`courseIntroduction`、`courseConclusion`、图片、PDF、视频、HTML、评价和未解决事项。每条课程目标还必须关联真实 Part 和能够留下结果的学习证据 Block。缺失或损坏的完整 PDF、未确认的实质设计、开放的阻塞事项、缺失媒体和待定视频时间码都会阻止“可上传”结论。

## 管理员检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate-course.py tests/fixtures/valid-course --json
python3 scripts/generate-html-report.py course/interactions/html/example.html --block-id example --source interactions/html/example.html --output-dir .course-work/html-reports
```

视频测试会在临时目录中动态构造只含必要元数据的极小 MP4，用于验证时长、H.264/AAC、faststart、长视频提醒和越界事件。仓库不包含课程样例视频，也不会安装或生成 MP4。

PDF fixture 是明确标注的结构测试材料，不冒充任何真实论文。验证器检查安全路径、`.pdf` 扩展名、`%PDF-` 文件头和 `invalid-pdf-header` / `invalid-pdf-eof` 等错误；真实平台中的逐页渲染仍需在上传前测试。

详细设计见 [平台课程标准化 Skills 设计](docs/superpowers/specs/2026-08-06-course-authoring-skills-design.md)，当前验证结果见 [验证报告](docs/validation-report.md)。
