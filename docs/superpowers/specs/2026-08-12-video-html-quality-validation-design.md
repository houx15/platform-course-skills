# 视频兼容性与 HTML 可读性检查设计

日期：2026-08-12

## 1. 目标

课程上传前必须确认视频满足平台播放合同，并为每个 HTML 交互生成可追溯的样式与合同检查报告。

本次新增两类质量门槛：

- 视频必须采用 MP4 封装、H.264 视频编码、AAC 音频编码，并开启 faststart；无法确认或不符合时阻止上传。
- HTML 的正文和控件不得低于 16px，明确标记的辅助文字不得低于 14px；无法静态确认或不符合时阻止上传。

时长超过 10 分钟和文件超过 500 MiB 属于显式警告，不单独阻止上传。课程仍须保留静态检查、真实浏览器验收和真实学习效果之间的证据边界。

## 2. 采用方案

采用混合检查：工具包内置无需外部依赖的确定性检查，并在环境存在 `ffprobe` 时补充权威媒体流信息。

没有采用以下方案：

- 只在 Skill 中提醒：无法稳定阻止不合格文件；
- 强制依赖 `ffprobe` 和浏览器：教师环境未必具备这些工具，基础验证不能因此完全失效。

内置检查与 `ffprobe` 结论冲突时，Review 阻止上传。HTML 静态检查通过不等于真实 iframe 已完成浏览器验收。

## 3. 数据与产物边界

`course.json` 继续作为学生课程的唯一事实源，不增加媒体技术检测字段，也不升级当前 `schemaVersion: "1.1"`。

视频检查结果进入 `validate-course.py --json` 的 issues/warnings，并成为整体 Review 的 `video` 证据。第一版不要求额外持久化视频报告。

每个 `interactiveHtml` Block 必须在作者工作区产生：

```text
.course-work/html-reports/
├── <block-id>.json
└── <block-id>.md
```

报告不得进入 `course/`。JSON 保存当前 HTML 的 SHA-256；文件变化后旧报告立即失效。ZIP 继续被忽略，验证器不得修改 MP4 或 HTML。

## 4. 视频确定性检查

### 4.1 容器与编码

每个课程视频必须满足：

- 相对路径安全且文件存在；
- 扩展名为 `.mp4`；
- 顶层 box 包含合法 `ftyp`；
- 所有视频轨都是 H.264，内置检查识别 `avc1` 或 `avc3` sample entry；
- 视频至少包含一条视频轨；
- 如果存在音轨，所有音轨均为 AAC，内置检查识别 `mp4a` sample entry；
- 静音视频可以没有音轨；
- `moov` 必须位于首个 `mdat` 之前；
- `mvhd` 可读取有效时长。

环境存在 `ffprobe` 时，同时读取 `format_name`、各流 `codec_type`/`codec_name`、时长与文件大小。`codec_name` 必须为 `h264` 和可选的 `aac`。内置解析与 `ffprobe` 任一方发现不合格或双方冲突均阻止上传。

如果内置检查无法可靠识别轨道，而 `ffprobe` 也不可用，返回无法验证的阻塞错误，不能仅凭扩展名放行。

### 4.2 faststart

faststart 的确定性判据是顶层 `moov` 出现在首个 `mdat` 之前。缺失 `moov`、缺失 `mdat` 或顺序错误均不能通过。

### 4.3 时长、大小与交互建议

- `duration > 600` 秒：产生 `long-video` warning；
- `size > 500 * 1024 * 1024` 字节：产生 `large-video` warning；
- 长视频无交互，或相邻边界间出现超过 600 秒的无交互区间：产生 `sparse-video-interactions` warning。

长视频报告必须包含总时长、文件大小、交互点数量、首尾交互位置和最大无交互间隔。Skill 根据脚本中的概念转换、证据出现、预测、判断和总结位置提出交互候选，不能机械地按固定分钟数插题。以上 warning 必须显示在 Review 中，但不单独改变 `uploadable` 状态。

### 4.4 视频错误码

阻塞错误：

| 错误码 | 含义 |
| --- | --- |
| `invalid-video-container` | 扩展名或内部容器不是 MP4 |
| `unsupported-video-codec` | 视频轨不是 H.264 |
| `unsupported-audio-codec` | 存在非 AAC 音轨 |
| `missing-faststart` | `moov` 不在首个 `mdat` 之前 |
| `video-profile-unverified` | 无法可靠确认容器或编码 |
| `video-tool-conflict` | 内置检查与 `ffprobe` 结论冲突 |
| `missing-file` | 视频文件不存在 |
| `invalid-video` | 文件损坏或无法读取 |

非阻塞警告：`long-video`、`large-video`、`sparse-video-interactions`。

## 5. 视频转换工作流

主课程 Skill 只检查、说明和协调，不自动修改老师的视频。检查失败时提供两个选项：

1. 推荐老师新开 Codex 会话专门处理大型视频；
2. 老师明确授权后，当前 Codex 可把有界转码任务交给 subagent。

无论采用哪一种方式：

- 保留原文件；
- 禁止覆盖输入；
- 输出到老师确认的目录，命名为 `<stem>-platform.mp4`；
- 只修复技术兼容性，不剪辑、不重排、不增加字幕、水印或片头片尾；
- 默认保留分辨率和帧率；
- 转码完成后重新运行完整媒体检查；
- 新视频验证通过后，主 agent 才能更新 `course.json` 并重新对齐交互时间；
- 没有 ffmpeg、没有空间或没有写权限时停止，不绕过限制。

推荐命令模板：

```bash
ffmpeg -n -i input-video \
  -map 0:v:0 -map 0:a? \
  -c:v libx264 \
  -pix_fmt yuv420p \
  -preset medium \
  -crf 23 \
  -c:a aac \
  -b:a 128k \
  -movflags +faststart \
  output-video-platform.mp4
```

`-n` 防止覆盖；`-map 0:a?` 允许静音视频。输出仍超过 500 MiB 时只提出进一步压缩方案，不擅自降低分辨率。

### 5.1 新会话 Prompt

Skill 必须提供以下可复制 Prompt，并代入老师的实际路径：

```text
请帮我把视频处理成课程平台兼容格式。

输入文件：
<原视频绝对路径>

输出目录：
<输出目录绝对路径>

要求：
1. 先使用 ffprobe 检查输入文件，报告容器、视频编码、音频编码、时长和文件大小。
2. 不得覆盖或修改原文件。
3. 输出文件命名为“原文件名-platform.mp4”。
4. 输出采用 MP4、H.264、yuv420p、AAC；原视频无音轨时保持静音；开启 faststart。
5. 不剪辑内容，不改变视频顺序，不添加字幕、水印或片头片尾。
6. 默认保留原始分辨率和帧率，使用 CRF 23、preset medium；不要擅自降低分辨率。
7. 使用不会覆盖已有文件的 ffmpeg 参数。
8. 完成后重新用 ffprobe 检查输出路径、容器、视频编码、音频编码、时长、大小、faststart 和与原视频的时长差异。
9. 如果输出仍超过 500 MiB，只提出进一步压缩方案，先不要继续处理。
```

### 5.2 Subagent 边界

只有老师明确说“请帮我处理”后才能委派。subagent 只能读取指定输入并在指定目录创建新文件，不能删除、移动或覆盖原视频，不能自行修改课程 JSON。主 agent 必须等待任务完成、核对输出并重新 Review。

## 6. HTML 字号合同

### 6.1 基础规则

- `html`/`body` 基础字号必须能静态确认至少为 16px；
- 正文、题目、选项、输入框、选择器、文本域和按钮至少为 16px；
- 所有可见文字绝对不得低于 14px；
- 14–15.99px 只允许用于 `.auxiliary` 或带 `data-text-role="auxiliary"` 的明确辅助文字；
- 控件必须显式继承合格基础字号，或显式设置至少 16px；
- `clamp()` 只有在可验证最小值满足对应下限时通过；
- `rem` 只有在根字号明确可换算时通过；
- 无法静态换算的 `em`、单独 `vw`、`calc()`、百分比或其他表达式阻止上传，并要求改为可验证写法。

合格示例：

```css
html,
body {
  font-size: 16px;
}

button,
input,
select,
textarea {
  font-size: inherit;
}

.auxiliary,
[data-text-role="auxiliary"] {
  font-size: 14px;
}

.title {
  font-size: clamp(24px, 3vw, 36px);
}
```

`font-size: 13px`、未标记正文的 `15px`、没有安全下限的 `2vw` 均不合格。

### 6.2 HTML 错误码

| 错误码 | 含义 |
| --- | --- |
| `missing-font-contract` | 没有可验证的基础字号 |
| `base-font-too-small` | `html`/`body` 小于 16px |
| `content-font-too-small` | 正文、题目或选项小于 16px |
| `control-font-too-small` | 输入控件或按钮小于 16px |
| `auxiliary-font-too-small` | 辅助内容小于 14px |
| `unmarked-small-text` | 14–15.99px 内容未标记为辅助文字 |
| `unverifiable-font-size` | 字号无法静态换算 |
| `missing-html-report` | 最终 Review 缺少报告 |
| `stale-html-report` | 报告文件摘要与当前 HTML 不一致 |

以上全部阻止上传。

## 7. HTML 报告合同

JSON 结构：

```json
{
  "schemaVersion": "1.0",
  "blockId": "urban-heat-island-check",
  "source": "interactions/html/urban-heat-island-check.html",
  "sha256": "<current-file-sha256>",
  "checks": [
    {
      "code": "base-font-size",
      "status": "pass",
      "evidence": "html/body 基础字号为 16px"
    }
  ],
  "finalStatus": "pass",
  "browserCheckRequired": true
}
```

不写生成时间，以保持确定性。Markdown 固定输出：

| 检查项 | 结果 | 证据与修改建议 |
| --- | --- | --- |
| HTML5 与自包含资源 | pass/revise | 具体证据 |
| 画布与横向溢出 | pass/revise | 具体证据 |
| 基础字号 | pass/revise | 具体证据 |
| 正文与题目 | pass/revise | 具体证据 |
| 选项与输入控件 | pass/revise | 具体证据 |
| 按钮 | pass/revise | 具体证据 |
| 辅助说明 | pass/revise | 具体证据 |
| 完成条件 | pass/revise | 具体证据 |
| 消息协议 | pass/revise | 具体证据 |
| 浏览器复核边界 | required | iframe 中待核查事项 |
| 最终结论 | pass/revise | 是否阻止上传 |

报告生成命令读取 Block ID、课程根目录和 HTML 路径，一次生成 JSON 与 Markdown。Review 核对 Block、路径、SHA-256、`finalStatus` 和当前确定性检查结果。报告缺失、失败、过期或与当前检查不一致均阻止上传。

报告属于作者工作记录，因此只有在 `validate-course.py` 收到 `--work-dir`、或 `review-platform-course` 执行完整 Review 时才强制要求。只拿到上传目录的独立验证仍会重新运行全部 HTML 静态合同与字号检查，并以非阻塞 limitation 明确报告“未提供作者工作区，无法核对持久化报告”；它不会把报告文件放入 `course/`。

## 8. Review 行为

整体 `video` 证据列出视频数量、每个视频的容器、视频/音频编码、faststart、时长、大小、交互数量、阻塞错误和 warning。

整体 `html` 证据列出 HTML 数量、每份报告路径、摘要一致性、合同检查、字号检查与浏览器复核边界。

状态规则：

- 视频格式不合格或无法确认：`缺少必要材料，暂不可上传`；
- HTML 字号不合格、报告缺失或过期：`缺少必要材料，暂不可上传`；
- 视频超过 10 分钟或 500 MiB：仍可上传，但 Review 必须显式显示 warning；
- 静态 HTML 通过只证明合同与可静态判断的字号，不证明真实 iframe 缩放、截断、对比度、操作可达性或学习效果。

## 9. Skills 行为变化

`analyze-course-materials`：记录视频文件类型、大小和长视频候选；不把扩展名当作编码证据。

`design-video-interactions`：读取实际时长；超过 10 分钟时主动检查交互密度，并根据脚本语义提出交互候选。

`design-course-html`：按字号合同生成 HTML，生成 `.course-work/html-reports/`，修复后重生成报告。

`build-platform-course`：在媒体设计后执行技术检查；失败时提供新会话 Prompt，只有明确授权才允许 subagent 转码。

`review-platform-course`：独立重新检查媒体，不接受 Builder 的口头通过结论；将格式错误、警告和浏览器证据边界分开报告。

## 10. 兼容与迁移

不升级 `course.json` 版本：

- 没有 video/HTML Block 的课程不受影响；
- 已有视频必须重新检查格式与 faststart；
- 已有 HTML 必须补齐字号合同并生成报告；
- 当前城市热岛 HTML 中的 13px 字号升级到至少 14px，正文和控件升级或继承 16px；
- 旧报告不能沿用；
- 仓库不新增、发布或安装样例 MP4；视频测试继续动态生成最小文件。

## 11. 测试设计

视频测试：

- H.264 + AAC + faststart 通过；
- 静音 H.264 + faststart 通过；
- HEVC/VP9 视频失败；
- MP3/Opus 音频失败；
- `moov` 位于 `mdat` 后失败；
- 缺轨或编码无法确认失败；
- `ffprobe` 与内置检查冲突失败；
- 超过 600 秒产生 warning；
- 长视频无交互或长间隔产生 warning；
- 超过 500 MiB 产生 warning；
- 验证过程从不修改输入视频。

HTML 测试：

- 16px 基础字号和控件通过；
- 明确辅助文字 14px 通过；
- 13px 失败；
- 未标记 15px 失败；
- 安全 `clamp()` 通过，不安全 `clamp()` 失败；
- 无法换算的单位失败；
- JSON/Markdown 报告确定性生成；
- HTML 修改后报告过期；
- 缺少报告阻止最终上传；
- 有效 fixture、`format/example_output` 和 `for_test.docx` 端到端课程更新后重新通过。

## 12. 验收标准

- 完整自动测试、Python 编译检查和差异检查通过；
- 标准 fixture、本地样例与 `for_test.docx` 课程均返回 `可上传`；
- HTML 报告存在且摘要匹配；
- 不合格视频被阻止；
- 长视频和大文件只产生明确 warning；
- Skill 提供可复制的 ffmpeg Prompt；
- subagent 只有在老师明确授权后才能转码；
- 原视频永远不被覆盖；
- 仓库不新增 ZIP 或 MP4；
- Review 明确区分格式合格、教学建议、浏览器验收边界与真实学习效果。
