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

然后提供需要处理的文件或目录。AI 会先理解材料并确认长视频、HTML 交互和课程结构，再逐步生成课程。

最终交付位于 `course/`；过程记录位于 `.course-work/`。只上传 `course/`，不需要 ZIP。

Review 会把 `.course-work/materials-extracted.json` 与 `source-coverage.json` 逐项对账，并验证每个去向确实是 `course.json` 中存在的 Block。未确认的实质设计、开放的阻塞事项、缺失媒体和待定视频时间码都会阻止“可上传”结论。

## 管理员检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate-course.py tests/fixtures/valid-course --json
```

视频测试会在临时目录中动态构造只含必要元数据的极小 MP4，用于验证时长读取和越界检测。仓库不包含课程样例视频，也不会安装或生成 MP4。

详细设计见 [平台课程标准化 Skills 设计](docs/superpowers/specs/2026-08-06-course-authoring-skills-design.md)，当前验证结果见 [验证报告](docs/validation-report.md)。
