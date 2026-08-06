# 平台课程标准化工具包

这套 Skills 帮助教师把已有的 Word、HTML、Markdown、文本及其他课程材料逐步整理为平台可处理、可追溯、可检查的标准课程。

## 下载与安装

要求 Python 3.9 或更高版本。

```bash
git clone https://github.com/houx15/platform-course-skills.git
cd platform-course-skills
python3 scripts/install-skills.py --target both
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

然后提供需要处理的文件或目录。AI 会先理解材料并确认长视频、HTML 交互和课程结构，再逐步生成课程。

最终交付位于 `course/`；过程记录位于 `.course-work/`。只上传 `course/`，不需要 ZIP。

Review 会把 `.course-work/materials-extracted.json` 与 `source-coverage.json` 逐项对账，并验证每个去向确实是 `course.json` 中存在的 Block。未确认的实质设计、开放的阻塞事项、缺失媒体和待定视频时间码都会阻止“可上传”结论。

## 管理员检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate-course.py tests/fixtures/valid-course --json
```

仓库中的 `video_example.mp4` 只用于验证 MP4 时长读取和越界检测，不是课程模板，也不会被安装到 Skill 目录。

详细设计见 [平台课程标准化 Skills 设计](docs/superpowers/specs/2026-08-06-course-authoring-skills-design.md)，当前验证结果见 [验证报告](docs/validation-report.md)。
