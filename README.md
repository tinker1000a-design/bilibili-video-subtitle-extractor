# b站视频转文稿

<img src="assets/banner.jpg" width="640" alt="鲸圆券 · DeepSeek token 银行">

给它一个 B 站视频链接，它给你一份带时间锚点的可读文稿。

- **有官方字幕轨** → 直接下载整理，**1-2 秒**出结果
- **没有字幕轨** → 先报告原因，显式加 `--transcribe` 才在本地转写（30 分钟约 10 分钟）
- 全程本地处理，音频不外传。做的是**语音转文字**，不做翻译、不用截图 / OCR

> **有 AI 助手？让它先读 [AGENTS.md](AGENTS.md)**：规则要求它同时给出「自己填凭据」和「全自动扫码」两个选项，你点头后它才会代你登录。扫码全程不用开开发者工具。

## 最短路径（看完这 8 行就能用）

```powershell
git clone https://github.com/tinker1000a-design/bilibili-video-subtitle-extractor.git
cd bilibili-video-subtitle-extractor
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
.\.runtime\Scripts\python.exe scripts\qr_login.py            # 扫码登录，30 秒
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>'   # 出稿
```

**下面当字典查**：装不上看「部署」，凭据搞不懂看「填 SESSDATA」，想给人读加 `--readable`，只想总结不用管任何参数。

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
2. 按 `scripts/requirements.lock` 安装完整依赖并校验下载哈希（耗时取决于网络与缓存）
3. 检查 ffmpeg 是否在 PATH（缺了只警告，原生字幕路线仍可用）

如果 PowerShell 拦住脚本，手动等价执行：

```powershell
uv venv --python 3.12 .runtime
uv pip sync --python .runtime/Scripts/python.exe --require-hashes scripts/requirements.lock
```

### 第 3 步：自检（不转写，只验环境）

```powershell
.\.runtime\Scripts\python.exe scripts\check_auth.py
.\.runtime\Scripts\python.exe scripts\digest.py 'https://www.bilibili.com/video/BV16vdHBPExG/'
```

- `check_auth.py` 打印 `{"status":"ok",...}` 就说明环境正常（此时 `auth` 多半是 `none`，还没登录）
- `digest.py` 的最后一行会区分成功、缺字幕、缺凭据或读取失败；未登录时通常是 `auth_missing`
- `error` 需结合错误阶段判断，可能来自环境、网络或站点，不能一概归因

首次跑语音转写时，才会下载 Whisper 模型（turbo 约 1.6 GB）到 `.models`，之后复用缓存。

### 第 4 步：装技能（让「发链接 + 总结」自动生效）

```powershell
.\.runtime\Scripts\python.exe scripts\install_skill.py
```

它读出 `skills/video-digest/SKILL.md`，把里面的 `{REPO}` 换成本机克隆路径，装进机器上**已经存在**的
助手技能目录（WorkBuddy / DeepSeek Harness / Claude Code / Codex / `.agents/skills`）。没有探测到目录时返回 `no_target`，需用 `--target` 明确指定，不会创建假定宿主的目录。

安装器只更新归属于当前克隆且未被手改的副本。同名技能来自其他克隆、没有安装标记或已被修改时，返回 `conflict`，本次所有目标均不写入。先查看目标，再明确替换：

```powershell
.\.runtime\Scripts\python.exe scripts\install_skill.py --target 'D:\助手\skills' --dry-run
.\.runtime\Scripts\python.exe scripts\install_skill.py --target 'D:\助手\skills' --replace-existing
```

替换前保留唯一命名的 `SKILL.<随机标识>.bak`，不会覆盖之前的备份。旧版本安装的无标记副本也需这一次明确迁移。

装好之后的行为：

| 你在新窗口里发 | 会不会自动走这套流程 |
|---|---|
| `https://www.bilibili.com/video/BVxxxx` + `总结` | ✅ |
| `https://b23.tv/xxxx` + `zj` | ✅ |
| `总结视频内容` / `总结视频` / `这个视频讲什么` / `提炼要点` | ✅ |
| 只发一个链接，什么都不说 | ✅（按「总结」处理） |

不用再提任何命令，也不用记得仓库在哪。

输出里 `first_time: true` 表示本机第一次装 —— 这时 AI 助手会按
[`docs/after-install.md`](docs/after-install.md) 在回复末尾附一段使用教程。
`bootstrap.ps1` 末尾会顺手调一次这个脚本，所以正常部署时你不需要单独跑它。

---

## 填 SESSDATA（唯一需要手动的一步）

B 站部分字幕轨只对登录用户开放。带与不带凭据的实测差距（同一个 29.5 分钟视频）：

| | 带 SESSDATA | 不带 |
|---|---|---|
| 耗时 | **1.5 秒** | 603 秒 |
| 简繁混用 | 0% | 3.46% |
| 同一地名 | 40 次全一致 | 7 种变体 |

### 两条路，选一条

| | 方式 | 耗时 | 需要什么 |
|---|---|---|---|
| **A** | 扫码登录（推荐） | 30 秒 | 手机 B 站 App |
| **B** | 手动复制 | 2 分钟 | 浏览器 F12 |

**A｜扫码**（不用碰开发者工具）：

```powershell
.\.runtime\Scripts\python.exe scripts\qr_login.py
```

也可以双击 `login-qr.bat`。生成 `.credentials\login_qr.png`，用 B 站 App 扫码并确认，token 自动写入。
⏱ 二维码实测约 **182 秒**过期（B 站侧限制）。先打开手机 App 再生成；过期就重跑，旧图立即作废。

**B｜手动复制**：`F12` → 应用/Application → Cookies → bilibili.com → 筛选 `sess` → **右键 `SESSDATA` → 复制值**。
⚠️ 屏幕上显示的是截断值，鼠标拖选只能拿到前 8 位，**必须走右键菜单**。逐步说明见 [docs/credentials.md](docs/credentials.md)。

> 走的是 B 站官方扫码接口，**不读浏览器 Cookie、不要密码、不要验证码**。代价是账号多一条登录设备记录，可在 App 里移除。

### 存到哪

```
<项目根目录>\.credentials\sessdata.txt
```

内容只有那一串（形如 `xxxx%2C1790000000%2Cxxx`，含 `%2C`，30-200 字符）。也接受 `SESSDATA=xxx` 或整条 cookie，会自动剥值；填成网址会明确报错。

不想开记事本：复制好 token 后双击 `save-sessdata.bat`，它从剪贴板取、自己剥值、写入并打印打码结果——token 不经过聊天窗口和命令行参数，不留 shell 历史。

### 验证

```powershell
.\.runtime\Scripts\python.exe scripts\check_auth.py
```

| 输出 | 含义 |
|---|---|
| `auth: valid` + 昵称 | ✅ 生效 |
| `auth: expired` | 有值但 B 站判定未登录 → 过期或被撤销 |
| `auth: none` | 文件不存在 / 空 / 解析不出 |
| `auth: unknown` | 网络不通，状态不明 |

SESSDATA 一般 **3 个月**过期。过期后 `digest.py` 返回退出码 4 且**不进入转写**（以前会把过期误判成「没字幕」，白跑一次）。一条命令自动续期：

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>' --relogin
```

细节（F12 逐项、粘贴格式表、验证输出全解、二维码机制）见 [docs/credentials.md](docs/credentials.md)。

---

## 日常用法

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>'
```

它会自己判断：有字幕就取字幕出稿；**没字幕就停下来告诉你原因**，不会擅自去下模型。

常用变体：

```powershell
# 允许本地转写（首次下载 1.6GB 模型，30 分钟视频约 10 分钟）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --transcribe

# 凭据过期时自动拉起二维码登录，扫完继续
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --relogin

# 已经有结果，只重生成文稿（改完 glossary.json 后用）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --reuse

# 给人读：段落缩到 70 字，另存 transcript-readable.md（不覆盖默认版）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --readable

# 校验只插入允许的语句标点：原有字符、数字与符号必须保留
.\.runtime\Scripts\python.exe scripts\check_punct.py outputs\<BV号>_p<分P号>\transcript.txt outputs\<BV号>_p<分P号>\transcript-readable-punct.txt

# 换模型：small 更快更差，turbo 默认
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --model small

# 指定凭据文件（一般不用，会自动读 .credentials\sessdata.txt）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --sessdata-file '路径'
```

脚本逐行输出 JSON，**只看最后一行**：

| `status` | 退出码 | 含义 | 该做什么 |
|---|---|---|---|
| `ok` | 0 | 出稿了 | 读 `markdown` 指向的文件 |
| `need_asr` | 2 | 当前提取器未发现字幕候选 | 看 `eta_minutes`，问用户要不要加 `--transcribe` |
| `auth_expired` | 4 | 凭据过期（nav 返回 -101） | 重新扫码，或加 `--relogin` 自动续期 |
| `auth_missing` | 4 | 匿名，看不到登录专属轨道 | 先登录；这不等于视频没字幕 |
| `auth_unverified` | 4 | nav 不通，状态不明 | 稍后重试，不要猜 |
| `native_failed` | 5 | 有字幕轨但下载全失败 | 重试一次 |
| `empty` | 3 | 字幕轨已读取，但解析后没有有效文字 | 如实说明，不自动转写 |
| `error` | 1 | 失败 | 读 stderr 的 `message`，判断网络/凭据/风控，别反复重试 |

### 术语纠错表

`glossary.json` 记录「错 → 对」的替换，用于修 ASR 的品牌名误听（实测 `Subatch`→`SubBatch`、`Notebook ALM`→`NotebookLM`）。发现新的误听就加一条，永久生效。

只收**英文专名**，不要收中文同音错——中文误替换的风险大于收益，交给上下文判断更稳。

术语表仅用于 ASR 的单独修订版 `transcript-corrected.txt`，逐段改动记录在 `transcript-corrections.json`。没有替换时不生成这两份文件。原生字幕不应用术语表；`transcript.txt` 始终保留原始字幕正文，Markdown 仅做简繁转换和分段。

分 P 视频按 BV＋分 P 号隔离。`--reuse` 对标准 URL／裸 BV 只读取本地缓存，不检查登录、不联网；旧版 BV 目录只有元数据匹配时才复用，缓存不匹配则报错。短链接首次解析仍需联网，离线复用时请使用标准 URL／裸 BV。

成功获取后由 `current-result.json` 指定本次采用的字幕来源，避免旧 ASR 抢占新原生字幕；旧缓存没有该标记时优先原生 `probe/`。通用站点同时记录输入地址和规范地址，用 `cache-index.json` 支持两种地址离线复用。ASR 保留这些身份字段。

三个入口统一使用「显式 `--sessdata-file` ＞ `BILI_SESSDATA` 环境变量 ＞ 默认凭据文件」的优先级。B 站凭据只用于 B 站任务，不影响其他站点。`--no-asr` 与 `--transcribe` 互斥，同时传入会报参数错误。

`check_punct.py` 只允许新增白名单中的语句标点和空白，保留原有非空白字符，并保护数字与英文词边界。`-1.5%` 变成 `15%` 等修改会被拒绝。请输出纯文本换行，不要用 `<br>` 或字面量 `\\n` 替代；检查通过仍不证明断句语义正确。

### 输出文件

每次运行在 `outputs/<BV号>_p<分P号>/` 下生成：

| 文件 | 内容 |
|---|---|
| `transcript.md` | **主产物**：标题 + 来源标记 + 分段正文（带 `[mm:ss]` 锚点） |
| `transcript.txt` | 原始字幕正文，不做简繁转换或术语替换，供补标点逐字回校 |
| `transcript-readable.md` | 加 `--readable` 才生成：段落 70 字，给人读的版本，不覆盖上面两份 |
| `probe/subtitles.srt` | SRT，可给播放器 |
| `probe/subtitles.json` | 每段文字 + 时间 + 置信度 |
| `probe/manifest.json` | 时长、来源方法、模型、耗时 |

`method` 字段标明文字从哪来：`native-caption`（站点字幕）、`native-auto-caption`（站点自动字幕）、`speech-recognition`（本地 ASR）。

### 分段是怎么切的，以及为什么没给无标点文稿加标点

两条来源的形态完全不同，实测（同一 29.5 分钟视频）：

| 来源 | 标点 | 分段依据 |
|---|---|---|
| 站点字幕轨 | **0 个**（B 站 AI 字幕不带标点） | 按字数累积：默认 120 字，`--readable` 70 字。段内是一长串无标点文字 |
| 本地 ASR | 162 个句号 + 420 个逗号 | 攒够长度后**等句末标点再断**，84% 的段尾落在标点边界 |

试过但行不通的路子：**用 cue 之间的时间空隙判断句子边界**。站点字幕轨的 cue 首尾相接，gap 中位数 0.00 秒、94% 的间隔就是 0，这个信号根本不存在。所以「按停顿断句」在这一类字幕上无效。

没有做「自动给无标点文稿加标点」，理由是实测会造出错误句界：把 `诗意的语言模糊，但是却完善了世界观` 断成 `…模糊，但是` + `却完善了世界观`，两句都读得通、但都不是原话。**误标点比没标点更容易误导人**。要真正加上标点，得引入中文标点恢复模型（约 250MB + 额外依赖），会把「3 秒部署」变成「几分钟部署」，与项目定位不符。

需要人读的时候用 `--readable`（更短的段 + 话语标记处提前断），或者自己在编辑器里顺手过一遍。

---

## 多 Agent 适配

同一份技能文件能直接装进多个助手，因为它们读的是两类公共约定，而不是各自的私有格式：

| 类型 | Agent | 怎么接 |
|---|---|---|
| 有技能目录 | WorkBuddy、DeepSeek Harness、Claude Code、Codex | `install_skill.py` 自动装（已覆盖） |
| 只读 AGENTS.md | Cursor、opencode、Aider、Zed、任意终端 Agent | 仓库根 `AGENTS.md`，在仓库目录下工作即可 |
| 不能执行命令 | ChatGPT 网页、豆包、扣子、Kimi 网页 | **拿不到字幕**，只能用 [adapters/transcript-summarizer.md](adapters/transcript-summarizer.md) 总结你贴进去的文稿 |

细节和扩展路径见 [adapters/README.md](adapters/README.md)。

**为什么不给每家写一个适配文件**：WorkBuddy / DSH / Claude Code 的 SKILL.md 格式本来就一样（frontmatter `name` + `description`，目录式布局），复制五份只会得到五个会互相漂移的副本。

---

## 给 AI 助手的接入说明

**完整协议见 [AGENTS.md](AGENTS.md)**——跨工具通用，Codex / Cursor / Claude Code 都会自动读它。
这里只列要点，细节以那份为准：

## 给 AI 助手的接入说明

**完整协议见 [AGENTS.md](AGENTS.md)**——跨工具通用，Codex / Cursor / Claude Code 会自动读它。这里只强调三条最容易出事的：

1. **需要凭据时同屏给两个选项**（你自己填 / 我来扫码），**只有你明确同意**才执行后者。「我不知道怎么弄」是求助，不是授权。
2. **默认不转写**。要转写必须你同意后显式 `--transcribe`，并先说明耗时与 1.6GB 模型体积。
3. **绝不读浏览器 cookie、不要密码或验证码、不代扫、不让用户在聊天里贴 token**；不把 `.credentials/` 或 token 写进任何提交。

状态码怎么读、错字怎么处理、引用怎么标、部署完怎么收尾——这些全在 AGENTS.md 里，那份是权威。

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
- [**VideoCaptioner**](https://github.com/WEIFENG2333/VideoCaptioner)（GPL-3.0）— 「断句交给 LLM、但强制回校比对」这个思路来自它；未复制任何代码，`check_punct.py` 是独立实现且判据更严

本项目代码由 **DeepSeek-V4.1-Flash 与 ChatGPT 6 Luna** 联合编译。

## 许可证

本项目源码以 [MIT License](LICENSE) 发布，可自由使用、修改、分发、商用，保留版权声明即可。
注意：MIT 只覆盖**本项目源码**，不覆盖你转写出来的视频文稿——那部分的版权仍属于原视频作者。

## 目录结构

```text
.
├─ scripts/                主代码（digest.py 是入口，其余是各环节脚本）
├─ skills/video-digest/    技能模板，{REPO} 占位由 install_skill.py 渲染
├─ adapters/               多 Agent 接法 + 给无命令能力 AI 的 prompt
├─ docs/                   使用教程、凭据细节、转写说明、发布流程
├─ references/             回退策略、实测记录
├─ .credentials/           凭据目录（sessdata.txt 不入库）
├─ AGENTS.md               AI 助手接入协议
├─ glossary.json           ASR 术语纠错表
├─ save-sessdata.bat       一键读剪贴板写入凭据
├─ login-qr.bat            双击扫码登录
└─ THIRD-PARTY-NOTICES.md  第三方组件、许可证与致谢
```

`scripts/` 下每个文件干什么看它头部的 docstring；依赖许可证见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

## 回归检查

```powershell
.\.runtime\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用合成字幕和网络替身，不读取真实账号凭据，也不下载模型。

GitHub Actions 在 Windows 和 Ubuntu 的 Python 3.12 上安装锁定依赖、检查导入并运行离线回归。发布步骤与人工验收范围见 [docs/releasing.md](docs/releasing.md)。
