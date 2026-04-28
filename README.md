<p align="center">
  <img src="static/video-use-banner.png" alt="video-use-zh" width="100%">
</p>

# video-use-zh

**中文视频剪辑工作流** — 基于 ffmpeg + FunASR 的图片/视频混剪管线。

在 `video-use` 原版基础上深度定制，专为中文内容和手机竖屏素材优化。

## 核心特性

- **中文语音识别** — FunASR paraformer-zh，自动转录 + 智能校对（地名、同音字、语境纠错）
- **照片 Ken Burns 动效** — ffmpeg zoompan 为静态照片添加缩放平移镜头运动
- **Pillow 文字叠加** — 半透明黑底白字 PNG overlay（解决系统 ffmpeg 无 drawtext 的问题）
- **Apple Music BGM** — 通过 gamdl 直接从 Apple Music 下载高质量背景音乐
- **Apple Silicon 硬件加速** — h264_videotoolbox 4K 预处理，渲染速度提升 3 倍+
- **竖屏画面处理** — 1080x1920 输出，横屏/竖屏/超竖屏素材统一处理（不拉伸、无黑边）
- **帧采样自检** — 关键时间点截图 + 视觉验证，确保成片质量

## 快速开始

### 环境要求

- macOS + Apple Silicon（M1/M2/M3）
- ffmpeg 编译版（安装到 `/usr/local/ffmpeg/`）
- Python 3.x + Pillow、numpy
- FunASR（中文语音识别）
- gamdl（可选，Apple Music BGM 下载）

### 安装

```bash
# 1. 克隆并注册到 Agent 的技能目录
git clone https://github.com/huangyebiaoke/video-use-zh.git ~/Developer/video-use-zh
ln -sfn ~/Developer/video-use-zh ~/.claude/skills/video-use-zh    # Claude Code
# ln -sfn ~/Developer/video-use-zh ~/.hermes/skills/video-use-zh  # Hermes

# 2. 安装依赖
cd ~/Developer/video-use-zh
uv sync                         # 或: pip install -e .
brew install ffmpeg             # 或用编译版 /usr/local/ffmpeg/

# 3. 配置 Apple Music cookies（如需下载 BGM）
# 需要 Apple Music 的有效 session cookies，详见 SKILL.md
```

### 使用

将素材放到一个文件夹里，告诉你的 Agent：

```bash
cd /path/to/your/photos_and_videos
claude    # 或 hermes 等
```

然后说：

> 帮我把这些素材剪成 60 秒的竖屏短视频

Agent 会自动：整理素材 → 推荐 BGM → 输出剪辑方案 → 等待确认 → 渲染 → 自检 → 交付成片。

## 工作流程

```
素材整理 → 选 BGM → 方案确认 → 渲染 → 帧采样自检 → 交付 → 迭代
```

1. **素材整理** — 收集照片和视频，分析分辨率、时长、方向
2. **BGM 选择** — 如无 BGM，推荐 2-4 首供用户选择（Suno 生成 / Apple Music 下载）
3. **方案确认** — 输出完整剪辑方案（镜头顺序、时长、文案、转场），等用户确认后执行
4. **渲染** — 按镜头逐段渲染（动效 + 文字叠加），最后拼接 + 混音
5. **帧采样自检** — 10 个关键时间点截图，视觉验证（无拉伸、文字清晰、比例正确）
6. **交付** — 发送成片，收集反馈
7. **迭代** — 根据反馈修改文案/素材/节奏，重新渲染

## 技术要点

### 中文 ASR 校对

FunASR 中文转录常见问题：
- **地名错误**：需搜索确认真实地名
- **同音字**：根据上下文修正
- **乱码**：结合语境还原正确文字
- **语境错误**：如"墓穴"→"洞穴"

修复范围：同时修复 `text` 字段和 `words[].text`（字幕重建依赖 word-level 数据）。

### 文字叠加方案

系统 ffmpeg 无 drawtext 支持，采用 **Pillow 生成裁剪版半透明黑底白字 PNG**：

```python
# Pillow 生成文字覆盖图 → ffmpeg overlay 叠加
ffmpeg -y -i base.mp4 -loop 1 -i overlay.png \
  -filter_complex "[1:v]trim=0:6,setpts=PTS-STARTPTS,fade=t=in:st=0:d=1:alpha=1[ov];\
     [0:v][ov]overlay=(W-w)/2:(H-h)/2:format=auto" \
  -c:v libx264 -pix_fmt yuv420p -r 30 output.mp4
```

**关键**：必须 `-loop 1`（否则 macOS ffmpeg 静默丢弃单帧 PNG）

### Ken Burns 动效

```bash
# 照片缓慢放大 + 平移，5 秒
ffmpeg -loop 1 -i photo.jpg \
  -vf "scale=1350:1800,\
       zoompan=z='min(zoom+0.003,1.3)'\
             :x='iw/2-(iw/zoom/2)+81*on/150.0'\
             :y='ih/2-(ih/zoom/2)+144*on/150.0'\
             :d=150:s=1080x1920:fps=30" \
  -t 5 output.mp4
```

**注意**：zoompan 不支持 `t` 变量，必须用 `on`（帧号）

### 画面比例处理

| 源画面 | 处理方式 |
|--------|---------|
| 竖屏 9:16 | `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920` |
| 横屏 16:9 | 先 `transpose=1` 旋转 90°，再放大裁剪 |
| 超竖屏 | 先缩放宽度，再裁掉上下多余部分 |

**原则**：放大裁剪填满，不变形、无黑边

### Apple Silicon 硬件加速

```bash
# 4K → 1080p 预处理（h264_videotoolbox）
ffmpeg -y -i input.MOV -vf scale=1920:-2 \
  -c:v h264_videotoolbox -profile:v high -pix_fmt yuv420p \
  -c:a aac input_1080p.mp4
```

4K 素材用 libx264 软编码极慢（~0.5x），硬件编码预处理后提升 3 倍+。

## 项目结构

```
video-use-zh/
├── SKILL.md              # 完整工作流文档（中文版）
├── README.md             # 本文件
├── install.md            # 安装指南
├── helpers/
│   ├── transcribe.py          # 中文语音识别
│   ├── transcribe_batch.py    # 批量转录
│   ├── pack_transcripts.py    # 转录结果打包
│   ├── render.py              # 渲染管线
│   ├── grade.py               # 调色
│   └── timeline_view.py       # 时间轴可视化
├── static/
│   ├── fonts/                 # 中文字体（Noto Sans CJK）
│   └── timeline-view.svg      # 时间轴示意图
└── skills/manim-video/        # Manim 动画技能（子技能）
```

## 已知限制

| 问题 | 解决方案 |
|------|---------|
| ffmpeg 无 drawtext | Pillow 生成 PNG + overlay |
| zoompan 不支持 `t` 变量 | 使用 `on`（帧号） |
| 4K HDR iPhone 视频编码慢 | h264_videotoolbox 预处理 |
| 横屏转竖屏需要旋转 | `transpose=1` + crop |
| overlay PNG alpha 异常 | 必须 `-loop 1` |

## License

MIT — 继承自原版 video-use

## 致谢

- [video-use](https://github.com/browser-use/video-use) — 原版视频剪辑工作流
- [FunASR](https://github.com/modelscope/FunASR) — 中文语音识别
- [gamdl](https://github.com/glomatico/gamdl) — Apple Music 下载
