# 平台课程标准化工具包

这套 Skills 帮助教师把已有的 Word、HTML、Markdown、文本及其他课程材料逐步整理为平台可处理、可追溯、可检查的标准课程。

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

然后提供需要处理的文件或目录。AI 会先提取材料并区分学生内容、教师设计、AI/系统规则、参考资料和拟排除内容；即使原文没有提到，也会明确询问是否需要长视频或 HTML 交互。

生成课程之前，AI 会给出完整的课程设计确认表：总共有多少 Part 和 Piece，并且一行对应一个 Piece，列出学生看到什么、教学重点、呈现方式、学生行动、完成标准以及资源或待确认项。老师确认整张表后才进入生成。AI 不会默认把每段材料变成 text block；如果认为需要流程图、示意图或信息图，只会先提出建议，得到老师明确同意后才生成。

最终交付位于 `course/`；过程记录位于 `.course-work/`。只上传 `course/`，不需要 ZIP。

course.json 和 index.md 只包含学生最终会看到的内容；教学设计、教师说明、AI 规则、平台实现和 source coverage 都留在 `.course-work/`。

Review 会先输出 Part 逐项 Review 表，分别检查每个 Part 的教学目标与结构、内容完整性、学生呈现、模态选择、练习与反馈、资源与格式；任一维度失败，该 Part 与整门课都不能判为可上传。随后输出整体 Review 表，检查所有 Part、来源分类与覆盖、资源、JSON、index、图片、视频、HTML、评价和未解决事项。未确认的实质设计、开放的阻塞事项、缺失媒体和待定视频时间码都会阻止“可上传”结论。

## 管理员检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate-course.py tests/fixtures/valid-course --json
```

视频测试会在临时目录中动态构造只含必要元数据的极小 MP4，用于验证时长读取和越界检测。仓库不包含课程样例视频，也不会安装或生成 MP4。

详细设计见 [平台课程标准化 Skills 设计](docs/superpowers/specs/2026-08-06-course-authoring-skills-design.md)，当前验证结果见 [验证报告](docs/validation-report.md)。
