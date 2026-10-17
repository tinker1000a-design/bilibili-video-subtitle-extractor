# b站视频转文稿

给它一个 B 站视频链接，它给你一份带时间锚点的可读文稿。

- **有官方字幕轨** → 直接下载整理，**1-2 秒**出结果，零错字
- **没有字幕轨** → 自动下音轨，本地 Whisper 转写兜底（30 分钟视频约 10 分钟）
- 全程本地处理，音频不上传任何第三方转写服务

> 本项目的音频回退路线是「音频转写（ASR）」，即语音转成文字。它**不做跨语言翻译**，也**不使用截图 / 抽帧 / OCR**。

---

## 部署（新电脑，照抄即可）

### 第 0 步：前置条件

Windows 10/11，PowerShell 可用。需要三样东西：

| 依赖 | 检查命令 | 没有就装 |
|---|---|---|
| uv | `uv --version` | `winget install --id=astral-sh.uv -e` |
| ffmpeg / ffprobe | `ffmpeg -version` | `winget install --id=Gyan.FFmpeg -e` |

Python **不用自己装**。初始化脚本会用 uv 拉一个 3.12 到项目内的 `.runtime`，不碰系统 Python。

### 第 1 步：克隆

```powershell
git clone https://github.com/tinker1000a-design/bilibili-video-subtitle-extractor.git
cd bilibili-video-subtitle-extractor
```

### 第 2 步：初始化隔离环境

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

成功会打印 `Ready: ...\.runtime\Scripts\python.exe`。这一步做三件事：

1. 建 `.runtime`（uv + Python 3.12，**不污染系统环境**）
2. 装 `scripts/requirements.txt` 里的依赖（约 4 秒）
3. 检查 ffmpeg 是否在 PATH（缺了只警告，原生字幕路线仍可用）

如果 PowerShell 拦住脚本，手动等价执行：

```powershell
uv venv --python 3.12 .runtime
uv pip install --python .runtime/Scripts/python.exe -r scripts/requirements.txt
```

### 第 3 步：自检（不联网转写，只探字幕）

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py 'https://www.bilibili.com/video/BV16vdHBPExG/' --no-asr
```

看到 `{"status":"need_asr",...}` 或 `{"status":"ok",...}` 就说明装好了。
看到 `{"status":"error",...}` 是网络或站点问题，不是安装问题。

首次跑语音转写时，才会下载 Whisper 模型（turbo 约 1.6 GB）到 `.models`，之后复用缓存。

---

## 唯一需要手动做的一步：填 SESSDATA

### 为什么必须填

B 站的 AI 字幕轨**默认只对登录用户开放**。匿名请求会返回 `need_login_subtitle: true`、0 条轨道——不是视频没字幕，是你没登录。

带登录态和不带的实测差距（同一个 29.5 分钟视频）：

| | 带 SESSDATA | 不带 |
|---|---|---|
| 耗时 | **1.5 秒** | 603 秒 |
| 简繁混用 | 0% | 3.46% |
| 同一地名写法 | 40 次全一致 | 7 种变体 |
| 术语正确率 | 高 | 错字明显 |

所以：**这 30 秒你不填，后面每个视频都要多等 10 分钟，还多一堆错字。**

### 去哪复制（关键：这步只能手动）

`SESSDATA` 带 `HttpOnly` 标记，**JS 读不到**，`document.cookie` 里根本不存在，任何在控制台里敲 `copy(document.cookie...)` 的写法都必然报
`Cannot read properties of undefined`。只能用面板：

1. 浏览器登录 `bilibili.com`，随便打开一个视频页
2. `F12` → 顶部选「**应用 / Application**」
3. 左侧「存储」→ **Cookies** → `https://www.bilibili.com`
4. 上方筛选框输入 `sess`，会让列表只剩一行
5. **右键点击 `SESSDATA` 那一行 → 复制 → 复制值（Copy value）**

> ⚠️ 屏幕上显示的值是**截断的**（形如 `1a2b3c4d%2C...`），用鼠标拖选只能拿到前 8 位。**必须走右键菜单。**

备选路线：`F12` → **Network** → 刷新页面 → 点任意请求 → Headers → Request Headers → 整条 `cookie:` 复制。本工具也支持整条 cookie，会自动剥出 SESSDATA。

### 粘到哪个文件

```
<项目根目录>\.credentials\sessdata.txt
```

文件内容**只有那一串**，形如：

```
xxxxxxxx%2C1790000000%2Cxxxxx%2Axx
```

判别标准：**含 `%2C`**，长度一般 30-40 字符（也可能到 200+），不含空格，不含 `http`。

三种写法都能被识别，粘错格式也不会炸：

| 你粘进去的 | 结果 |
|---|---|
| `xxxxxxxx%2C...`（裸 token） | ✅ 直接用 |
| `SESSDATA=xxxxxxxx%2C...` | ✅ 自动剥出值 |
| `buvid3=AAA; SESSDATA=xxx; bili_jct=yyy`（整条 cookie） | ✅ 自动剥出值 |
| 视频网址 | ❌ 明确报错，不会静默失败 |

### 一键方式（推荐，不用开记事本）

复制好 token 后，双击项目根目录的：

```
save-sessdata.bat
```

按任意键 → 脚本自己从剪贴板取、自己剥值、自己写进 `.credentials\sessdata.txt`，并打印打码后的结果供你核对：

```
[OK] saved to ...\.credentials\sessdata.txt
     token: 7686...a1b2  (222 chars)
     format looks correct (contains %2C)
```

这个方式的好处：token 直接从剪贴板进文件，**不经过聊天窗口、不经过命令行参数**（不会留在 shell 历史里）。

### 验证是否生效

跑任意视频，看输出里的 `auth` 字段：

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>' --no-asr
```

- `{"status":"probing", ..., "auth":"sessdata"}` → ✅ 生效
- `{"status":"probing", ..., "auth":"anonymous"}` → ❌ 文件为空或格式不对

未配置时脚本也会主动提示该去哪个文件填，不会让你猜。

### 失效是什么样

B 站发的 SESSDATA 有效期通常 **3 个月**（可在 DevTools 的 Expires 列直接看到）。失效不会报错，只会**静默退回匿名**：`auth` 变回 `anonymous`、又出现 `subtitle_login_required`、开始走 ASR 变慢。重新复制一次覆盖即可。

---

## 日常用法

一条命令，全自动：

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>'
```

它会自己判断：有字幕就取字幕，没字幕就转写，最后统一输出简繁规范、段落重组、带 `[mm:ss]` 锚点的文稿。

常用变体：

```powershell
# 只探有没有现成字幕，不转写（秒回）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --no-asr

# 已经有结果，只重生成文稿（改完 glossary.json 后用，不重跑转写）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --reuse

# 换模型：small 更快更差，turbo 默认
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --model small

# 指定凭据文件（一般不用，会自动读 .credentials\sessdata.txt）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --sessdata-file '路径'
```

脚本逐行输出 JSON，**只看最后一行**：

| `status` | 含义 | 该做什么 |
|---|---|---|
| `ok` | 完成 | 读 `markdown` 指向的文件 |
| `need_asr` | 要转写（命令仍在继续跑，除非加了 `--no-asr`） | 带 `eta_minutes`，可先告知预计耗时 |
| `need_asr` + `--no-asr` | 没有现成字幕 | 问用户要不要花时间转写 |
| `empty` | 拿到轨道但没文字 | 如实说明，不要编 |
| `error` | 失败 | 读 stderr 的 `message`，判断网络/凭据/风控，别反复重试 |

### 术语纠错表

`glossary.json` 记录「错 → 对」的替换，用于修 ASR 的品牌名误听（实测 `Subatch`→`SubBatch`、`Notebook ALM`→`NotebookLM`）。发现新的误听就加一条，永久生效。

只收**英文专名**，不要收中文同音错——中文误替换的风险大于收益，交给上下文判断更稳。

### 输出文件

每次运行在 `outputs/<BV号>/` 下生成：

| 文件 | 内容 |
|---|---|
| `transcript.md` | **主产物**：标题 + 来源标记 + 分段正文（带 `[mm:ss]` 锚点） |
| `transcript.txt` | 纯文本版，方便丢给别的工具 |
| `probe/subtitles.srt` | SRT，可给播放器 |
| `probe/subtitles.json` | 每段文字 + 时间 + 置信度 |
| `probe/manifest.json` | 时长、来源方法、模型、耗时 |

`method` 字段标明文字从哪来：`native-caption`（站点字幕）、`native-auto-caption`（站点自动字幕）、`speech-recognition`（本地 ASR）。

---

## 给 AI 助手的接入说明

如果你是拿到这个仓库的大模型，按这个顺序做，不要跳步：

1. **先检查前置**：`uv --version`、`ffmpeg -version`。缺 uv 就别往下走，先让用户装。
2. **跑初始化**：`powershell -File .\scripts\bootstrap.ps1`。不要用系统 Python 装依赖，不要 `pip install -g`。
3. **检查凭据**：看 `.credentials\sessdata.txt` 是否存在且非空。
   - 不存在或为空 → **停下来提醒用户填**，告诉他去 `F12 → Application → Cookies → bilibili.com → 筛 sess → 右键 SESSDATA → 复制值`，粘到 `.credentials\sessdata.txt`（或双击 `save-sessdata.bat`）。
   - **不要**自己尝试读浏览器 cookie、解密 cookie 数据库、或从任何地方抓取登录态。这一条没有例外。
4. **先探后跑**：`digest.py '<url>' --no-asr` 看 `auth` 是不是 `sessdata`。是 `anonymous` 就先回到第 3 步。
5. **然后才跑正式命令**，读最后一行 JSON 的 `markdown` 路径。
6. **文稿里的错字**：英文品牌名误听 → 追加到 `glossary.json` 再 `--reuse`；中文同音错 → 按语义修正，并在回复末尾列出改了哪些，不要静默改。
7. **数字类内容不自行补齐**：前后矛盾就指出矛盾（比如同一数字在两处出现不同值），不要二选一。
8. **引用给时间点**：`transcript.md` 每段前都有 `[mm:ss]`，按它标注。

硬性禁止：

- ❌ 把 `sessdata.txt` 的内容打印到对话、日志、commit 里
- ❌ 把 `.credentials/` 或 token 写进任何提交
- ❌ 修改 `.gitignore` 让凭据可被追踪
- ❌ 绕过登录、付费、DRM 限制；不遍历播放列表、不批量爬站
- ❌ 拿不到字幕时用猜测内容填空

凭据目录的说明文件是 `.credentials/README.txt`，和本节内容一致。

---

## 技术细节

```text
视频链接
  ├─ 有可访问的字幕轨道 → 下载并整理字幕
  └─ 无可访问的字幕轨道 → 获取公开音轨 → 本地 Whisper 转写
                                           ↓
                              TXT / SRT / JSON + 来源说明
```

- **B 站**：三跳 API（`web-interface/view` 取 CID → `player/wbi/v2` 查字幕轨 → `player/playurl` 取 DASH），音轨取最低码率（转写不需要高音质）。
  实测该 wbi 接口**带登录态裸调可通**，无需 wbi 签名实现。
- **其他站点**：`--generic` 走 yt-dlp 通用路线，实际支持取决于其站点适配；主要实测对象是 Bilibili。
- **转写**：faster-whisper，默认 multilingual `turbo` 模型，CPU int8。

也可以只用底层脚本（不做简繁规范和段落重组）：

```powershell
# 只要原生字幕
.\.runtime\Scripts\python.exe scripts\fetch_subtitles.py '<链接>' --native-only --work work\x --out outputs\x

# 强制走 yt-dlp 通用路线 + 转写
.\.runtime\Scripts\python.exe scripts\fetch_subtitles.py '<链接>' --generic --transcribe --work work\x --out outputs\x

# 已有音频文件，直接转写
.\.runtime\Scripts\python.exe scripts\transcribe_audio.py 'audio.m4a' --language zh --work work\x --out outputs\x
```

ASR 结果恒标记 `review_required=true`，并按 `avg_logprob < -0.6` / `no_speech_prob > 0.5` 生成 `review_candidates`。
**注意：`review_candidates` 为空不代表准确**——实测中文场景下该过滤器几乎不触发，专名同音错全都能漏过去。

---

## 实测数据（2026-10-17，Windows，CPU int8）

对象：`BV1yo4y1Q7eD`《【万字解析】极乐迪斯科究竟讲了一个什么故事》，1770.7 秒 / 29.5 分钟

| 指标 | 原生字幕（带登录态） | 本地 ASR（匿名） |
|---|---|---|
| 耗时 | **1.5 秒** | 603 秒（约 2.9x 实时） |
| 段数 / 汉字数 | 846 / 9202 | 638 / 9966 |
| 繁体异形字占比 | **0.00%** | 3.46%（345 字 / 19.7% 的行） |
| 同一地名写法 | **40 次全一致** | 7 种变体，最高频写法仅占 36% |
| 术语 | `叙事方式`/`寡头`/`星际拓荒` 全对 | `驱使方式`/`寡仇`/`星际阔荒` |

另一例：`BV1UEzEB8Eiu`（224 秒）全链路 70 秒完成，10 段 1170 字。

首次依赖安装与模型下载不计入上述耗时。这是单机实测，不是跨机器或全站点保证。
原生字幕本身也有局限：**无标点**（B 站 AI 字幕通病）、偶发同音错，但无简繁混用、专名一致，整体质量远高于 ASR。

---

## 数据与使用范围

- 模型下载需要联网；**转写全程本地进行**，音频不上传任何远程转写服务
- 项目**不自动读取浏览器 cookie**，不绕过登录、付费、DRM；登录态由你手动提供
- 工作目录、输出、音视频、模型权重、隔离环境、凭据均已列入 `.gitignore`
- 仅在你有权获取和处理相应音视频时使用；转写文稿的版权归属仍属于原视频作者

依赖项目：[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2](https://github.com/OpenNMT/CTranslate2)、[PyAV](https://github.com/PyAV-Org/PyAV)、[opencc](https://github.com/BYVoid/OpenCC)。各自适用其许可证。

## 致谢

这个工具站得比较高的地方全是别人的肩膀。完整清单（含许可证与义务）见 **[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)**，几个关键角色：

- [**faster-whisper**](https://github.com/SYSTRAN/faster-whisper) 与 [**CTranslate2**](https://github.com/OpenNMT/CTranslate2) — 能在一台普通 CPU 电脑上把 30 分钟音频转成文字，靠的是它们
- [**OpenAI Whisper**](https://github.com/openai/whisper) — `large-v3-turbo` 权重，MIT 许可
- [**yt-dlp**](https://github.com/yt-dlp/yt-dlp) — 非 B 站站点的通用路线，本作品的最大功臣之一，且是公有领域
- [**OpenCC**](https://github.com/BYVoid/OpenCC) — 简繁归一，靠它才能消除 ASR 的繁体异形字
- [**PyAV**](https://github.com/PyAV-Org/PyAV) 与 FFmpeg — 音视频解码
- [**uv**](https://github.com/astral-sh/uv) — 让部署从「配环境两小时」变成三秒

## 许可证

本项目源码以 [MIT License](LICENSE) 发布，可自由使用、修改、分发、商用，保留版权声明即可。
注意：MIT 只覆盖**本项目源码**，不覆盖你转写出来的视频文稿——那部分的版权仍属于原视频作者。

## 目录结构

```text
.
├─ scripts/
│  ├─ digest.py            一条命令跑完全流程（主入口）
│  ├─ save_sessdata.py     从剪贴板写入 SESSDATA
│  ├─ fetch_subtitles.py   字幕轨道 / 音轨获取与编排
│  ├─ transcribe_audio.py  faster-whisper 封装
│  ├─ subtitle_io.py       5 种字幕格式解析与写出
│  ├─ bootstrap.ps1        建 .runtime 隔离环境
│  └─ requirements.txt     精确固定版本
├─ .credentials/
│  ├─ README.txt           凭据填写说明（入库）
│  └─ sessdata.txt         ← 你手动填这一个（不入库）
├─ glossary.json           ASR 术语纠错表
├─ save-sessdata.bat       一键读剪贴板写入凭据
├─ skills/video-digest/    可直接装进 AI 助手的 skill 定义
├─ SKILL.md                底层取字链路的 Codex skill 定义
├─ LICENSE                 MIT
├─ THIRD-PARTY-NOTICES.md  第三方组件、许可证与致谢
├─ docs/  references/      音频转写说明、回退策略、实测记录
└─ agents/openai.yaml      agent 配置
```
