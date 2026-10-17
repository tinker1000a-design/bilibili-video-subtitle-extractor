# b站视频字幕提取

原生字幕优先；当前权限下取不到字幕时，获取公开音轨并在本地进行语音转文字。支持命令行运行，也附带可复用的 Codex skill。

**本项目的音频回退路线是“音频转写（ASR）”，即语音转成文字。它不做跨语言翻译，也不等于下载了作者上传的原始字幕。** 不使用截图、抽帧或 OCR 获取字幕。

## 工作流程

```text
视频链接
  ├─ 有可访问的字幕轨道 → 下载并整理字幕
  └─ 无可访问的字幕轨道 → 获取公开音轨 → 本地 Whisper 转写
                                           ↓
                              TXT / SRT / JSON + 来源说明
```

- B站：解析 BV、分 P 的 CID，查询字幕轨道。需要登录的轨道在当前未登录状态下可能不可读；这不证明视频没有字幕。
- 音频：DASH 播放优先只下载音轨；如果站点只提供音视频混合文件，可能需要取得该文件再提取音轨。
- 转写：使用 faster-whisper，默认 multilingual `turbo` 模型，CPU int8。本地进行识别，首次下载依赖和模型，后续复用缓存。
- 其他站点：提供 yt-dlp 通用路线，实际支持情况取决于其网站适配；主要实测对象是 Bilibili。

## 快速开始：Windows / PowerShell

### 前置条件

- Python 3.12（初始化脚本可通过 uv 选择或准备该版本）
- [uv](https://docs.astral.sh/uv/) 已加入 PATH
- [FFmpeg](https://ffmpeg.org/) 的 `ffmpeg`、`ffprobe` 已加入 PATH

下载项目并进入项目目录，然后执行：

```powershell
./scripts/bootstrap.ps1
```

初始化会在项目目录建立隔离环境 `.runtime`，不需要修改系统 Python 的包。若本机的 PowerShell 执行策略阻止脚本，可手动执行相同的初始化步骤：

```powershell
uv venv --python 3.12 .runtime
uv pip install --python .runtime/Scripts/python.exe -r scripts/requirements.txt
```

### 一条命令获取文字

```powershell
& ./.runtime/Scripts/python.exe scripts/fetch_subtitles.py 'https://www.bilibili.com/video/BV16vdHBPExG/' --transcribe --language zh --work work/example --out outputs/example
```

`--transcribe` 表示：没有可读的原生字幕时，自动下载音轨并转写。去掉该参数，回退路线只会取得音轨，返回 `audio_ready`，不会生成转写文字。

每个视频使用独立的 `--work` 和 `--out` 目录；处理分 P 视频时，在链接中保留 `?p=2` 等参数。

## 常见用法

只查询原生字幕，不下载音频：

```powershell
& ./.runtime/Scripts/python.exe scripts/fetch_subtitles.py '视频链接' --native-only --work work/native --out outputs/native
```

显式使用 yt-dlp 通用路线：

```powershell
& ./.runtime/Scripts/python.exe scripts/fetch_subtitles.py '视频链接' --generic --transcribe --work work/generic --out outputs/generic
```

已经有音频文件时，直接转写，无需重新获取视频：

```powershell
& ./.runtime/Scripts/python.exe scripts/transcribe_audio.py 'audio.m4a' --language zh --work work/local-asr --out outputs/local-asr
```

默认模型为 `turbo`。可以用 `--model small` 选择较小、较快的模型；本次案例中 small 有更多同音词错误。`--language auto` 可自动识别语言。更多参数见各脚本的 `--help`。

## 输出文件与来源

| 文件 | 内容 |
|---|---|
| `subtitles.txt` | 带时间范围的可读文字 |
| `subtitles.srt` | 可供播放器使用的 SRT 分段 |
| `subtitles.json` | 文字、时间和提取来源等元数据 |
| `manifest.json` | 时长、方法、模型、耗时及复查状态 |

`method` 用来区分文字来源：

| 值 | 含义 |
|---|---|
| `native-caption` | 网站提供的字幕轨道 |
| `native-auto-caption` | 网站提供的自动字幕轨道 |
| `speech-recognition` | 本地从音轨重新识别的文字 |

音频识别结果始终标记 `review_required=true`。专名、数字、缩写和同音词可能出错；SRT 时间是模型估计的分段时间，没有做人工逐字对齐。`review_candidates` 为空也不代表完全准确。

详细介绍见 **[音频转写说明](docs/audio-transcription.md)**。

## 作为 Codex skill 使用

项目根目录的 `SKILL.md` 描述了同一条获取链路。将本项目放入 Codex 的技能目录，并将文件夹命名为 `video-subtitle-fetcher`，即可显式请求：

```text
使用 $video-subtitle-fetcher 获取这个视频链接的字幕。
```

默认任务止于获取文字；理解内容、总结观点或事实核验由用户另行提出。

## 实测情况

2026-10-17，在一台 Windows 电脑上处理约 203 秒的中文视频：

- 公开音轨约 1.6 MB，取得音轨约 1–2 秒。
- 缓存模型后，small 的模型加载与转写约 37 秒；turbo 约 60 秒。
- `turbo` 产生 100 个 ASR 分段；这不代表原始视频有 100 条字幕。
- SRT、VTT、Bilibili JSON、JSON3、TTML 的格式解析，以及 TXT/SRT/JSON 写出已检查。

首次依赖安装、模型下载时间未计入上述转写耗时。此数据是单个案例，不是跨机器或所有站点的速度保证。详细边界见 [实测记录](references/validation.md)。

## 数据与使用范围

模型下载可能需要联网；本地识别不把音频上传给远程转写服务。项目不会自动读取浏览器 cookie，也不绕过登录、付费或 DRM 限制。

工作目录、输出字幕、音视频、模型权重、隔离环境和凭据已列入 `.gitignore`，不属于项目源码。仅在你有权获取和处理相应音视频时使用。

依赖项目：[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2](https://github.com/OpenNMT/CTranslate2)、[PyAV](https://github.com/PyAV-Org/PyAV)。依赖与模型适用各自的许可证。
