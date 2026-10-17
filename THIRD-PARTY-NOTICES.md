# 第三方组件与致谢

本项目的价值大部分建立在别人的工作上。这个文件说明**用了谁的东西、什么许可证、需要承担什么义务**。

许可证信息读取自本机已安装包的元数据（`importlib.metadata`）与各包自带的 LICENSE 文件，不是凭印象填写。

---

## 一、运行时依赖（随 `scripts/requirements.txt` 精确锁定版本）

| 组件 | 锁定版本 | 许可证 | 在本项目中的作用 |
|---|---|---|---|
| [requests](https://github.com/psf/requests) | 2.34.2 | Apache-2.0 | 调用 B 站接口、下载字幕与音轨 |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 2026.8.19 | **Unlicense（公有领域）** | 非 B 站站点的通用下载路线 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 1.2.1 | MIT | 本地语音识别封装 |
| [PyAV](https://github.com/PyAV-Org/PyAV) | 16.0.1 | BSD-3-Clause | 音视频解码；**其 wheel 内置 FFmpeg 共享库** |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | 4.8.3 | MIT | Whisper 的推理引擎 |
| [onnxruntime](https://github.com/microsoft/onnxruntime) | 1.31.0 | MIT | 运行 VAD（语音活动检测）模型 |
| [NumPy](https://github.com/numpy/numpy) | 2.5.4 | BSD-3-Clause | 底层数值计算 |
| [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) | 0.1.7 | Apache-2.0 | 繁体→简体归一（消除 ASR 简繁混用） |
| [tokenizers](https://github.com/huggingface/tokenizers) | 0.23.3 | Apache-2.0 | 间接依赖（Whisper 分词） |
| [huggingface-hub](https://github.com/huggingface/huggingface_hub) | 2.2.0 | Apache-2.0 | 间接依赖（模型下载） |
| [tqdm](https://github.com/tqdm/tqdm) | 4.70.1 | MPL-2.0 AND MIT | 间接依赖（进度条） |
| [protobuf](https://github.com/protocolbuffers/protobuf) | 7.36.2 | BSD-3-Clause | 间接依赖（onnxruntime） |

**需要注意的义务**：

- **PyAV 的 wheel 里打包了 FFmpeg 共享库**（`av.libs/avcodec-*.dll`、`avformat-*.dll`），FFmpeg 采用 LGPL-2.1+。如果你把整个 `.runtime` 目录连同本项目一起分发给别人，需要一并遵守 LGPL 条款（保留许可证声明、允许替换该库）。
- `tqdm` 是 MPL-2.0，属文件级弱 copyleft，不改它源码就无额外义务。
- 其余均为宽松许可证（MIT / BSD / Apache-2.0 / 公有领域），保留版权与许可声明即可。

## 二、模型权重

| 模型 | 许可证 | 说明 |
|---|---|---|
| `Systran/faster-whisper-large-v3-turbo` | MIT（继承自 OpenAI Whisper） | 由 OpenAI `whisper-large-v3-turbo` 转换而来，首次运行自动下载到 `.models`，**不随仓库分发** |
| Silero VAD | MIT | 由 onnxruntime 加载，用于语音活动检测 |

模型权重体积较大，`.gitignore` 已排除 `.models/`，因此本仓库不分发任何权重文件。

## 三、外部程序（不打包、不入库）

| 程序 | 许可证 | 何时需要 |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) | Apache-2.0 OR MIT | 仅部署阶段：建 `.runtime` 隔离环境 |
| Python 3.12 | PSF-2.0 | 同上，由 uv 拉取 |
| [FFmpeg](https://ffmpeg.org/) | LGPL-2.1+ / GPL-2.0+（取决于构建） | 仅音频下载与转写路径需要；纯字幕路线不依赖 |

这些由使用者自行安装，本项目不重新分发。

## 四、接口与格式规范

- **B 站 Web 接口**：`x/web-interface/view`、`x/player/wbi/v2`、`x/player/playurl` 均**不是官方公开文档接口**，实现依据站点前端请求的可观察行为。接口可能随时变更，本项目对此不做保证。
- **字幕格式**：SRT、WebVTT、B 站 JSON、JSON3、TTML 的解析按各自公开规范实现。
- 本项目与哔哩哔哩（bilibili）官方无任何关联，未获其授权或背书。

## 五、本仓库自己实现的部分

本仓库的代码由 **DeepSeek-V4.1-Flash 与 ChatGPT 6 Luna** 联合编译，从零编写，未复制其他同类项目的源码。

以下为本项目源码，按 [MIT](LICENSE) 发布：

- `scripts/digest.py` — 一条命令的主流程编排、段落重组、术语替换、文稿生成
- `scripts/save_sessdata.py` — 从剪贴板读取并规范化登录凭据
- `scripts/fetch_subtitles.py` — B 站绑定逻辑、字幕轨优先级、音轨回退编排
- `scripts/subtitle_io.py` — 5 种字幕格式解析与写出
- `scripts/transcribe_audio.py` — faster-whisper 调用与流式进度
- `scripts/bootstrap.ps1` — 隔离环境初始化
- `glossary.json`、`save-sessdata.bat`、文档与 skill 定义

## 六、如果你发现遗漏

本文件是基于「本仓库当前包含的代码与依赖」整理的。如果你发现某段代码实际来自其他项目、或某个依赖未被列出，请在仓库 Issues 中指出，我们会补上署名与许可证说明。

反过来也请使用者注意：**上游依赖的许可证以各自仓库为准**，本文件只是索引，不替代它们的许可证原文。
