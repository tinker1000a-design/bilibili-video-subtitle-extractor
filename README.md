# b站视频转文稿

给它一个 B 站视频链接，它给你一份带时间锚点的可读文稿。

- **有官方字幕轨** → 直接下载整理，**1-2 秒**出结果，零错字
- **没有字幕轨** → 自动下音轨，本地 Whisper 转写兜底（30 分钟视频约 10 分钟）
- 全程本地处理，音频不上传任何第三方转写服务

> 本项目的音频回退路线是「音频转写（ASR）」，即语音转成文字。它**不做跨语言翻译**，也**不使用截图 / 抽帧 / OCR**。

> **身边有 AI 助手？先让它读 [AGENTS.md](AGENTS.md)。**
> 那份文件定义了本项目的交互规则：它必须**同时**给你「自己填凭据」和「全自动部署」两个选择，且**只有你明确点头**才允许代你登录。
> 不想折腾 F12 的人可以选自动——它装好环境后给你一个二维码，你用 B 站 App 扫一下并确认即可，全程不用开开发者工具。

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

### 第 3 步：自检（不转写，只验环境）

```powershell
.\.runtime\Scripts\python.exe scripts\check_auth.py
.\.runtime\Scripts\python.exe scripts\digest.py 'https://www.bilibili.com/video/BV16vdHBPExG/'
```

- `check_auth.py` 打印 `{"status":"ok",...}` 就说明环境正常（此时 `auth` 多半是 `none`，还没登录）
- `digest.py` 打印 `{"status":"ok",...}` 或 `{"status":"need_asr",...}` 都算装好了
- 打印 `{"status":"error",...}` 是网络或站点问题，不是安装问题

首次跑语音转写时，才会下载 Whisper 模型（turbo 约 1.6 GB）到 `.models`，之后复用缓存。

### 第 4 步：装技能（让「发链接 + 总结」自动生效）

```powershell
.\.runtime\Scripts\python.exe scripts\install_skill.py
```

它读出 `skills/video-digest/SKILL.md`，把里面的 `{REPO}` 换成本机克隆路径，装进机器上**已经存在**的
助手技能目录（WorkBuddy / Claude Code / Codex / Cursor），不会给没装的工具造空目录。

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

### 两条路：自己复制，或者扫码

**A｜手动复制**——要开 F12 面板，2 分钟，见下一节。

**B｜扫码登录**——不用碰任何开发者工具，30 秒：

```powershell
.\.runtime\Scripts\python.exe scripts\qr_login.py
```

也可以直接双击 `login-qr.bat`。它会生成二维码图片 `.credentials\login_qr.png` 并一直等你：

1. 用手机 B 站 App 扫这个码（或扫 `login_qr.png`）
2. 手机上点「确认登录」
3. 脚本自动把 SESSDATA 写进 `.credentials\sessdata.txt`，打印 `{"status":"ok"}`

> ⏱ 二维码**只有约 3 分钟有效期**（实测 182 秒被判过期，是 B 站侧的限制，不是脚本设的）。
> 所以最好先把手机准备好、B 站 App 打开，再生成二维码。过期了就重跑一次，旧图立即作废。


口径说明：这走的是 B 站官方的扫码登录接口，**不读浏览器 Cookie、不要密码、不要验证码**。代价是你的账号会多一条登录设备记录，不想要了在 App 里随时移除。

> 如果你是让 AI 助手来装这个项目，它应该**同时**把 A 和 B 摆给你，并在你明确点头后才执行 B。规则写在 [AGENTS.md](AGENTS.md)。

### 去哪复制（方案 A：关键，这步只能手动）


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

```powershell
.\.runtime\Scripts\python.exe scripts\check_auth.py
```

| 输出 | 含义 |
|---|---|
| `{"auth":"valid","uname":"你的昵称","action":"ready"}` | ✅ 真的生效了 |
| `{"auth":"expired","action":"login_required"}` | 文件里有值，但 B 站判定未登录 → 已过期或被撤销 |
| `{"auth":"none","action":"login_required"}` | 文件不存在 / 为空 / 解析不出 |
| `{"auth":"unknown","action":"retry_later"}` | 网络不通，状态不明 |

### 过期会怎样（现在能认出来了）

B 站发的 SESSDATA 有效期一般 **3 个月**左右（可在 DevTools 的 Expires 列看到）。

**以前它是静默的**：过期后接口只是返回空字幕列表，和「这个视频没有字幕」长得一模一样，
工具就误以为没字幕，白跑一次转写。现在会先问 `nav` 接口，所以能直接说清是哪种：

| 情况 | 现在的表现 |
|---|---|
| 没有文件 / 文件空 | `auth: none`，提示去登录 |
| 有值但过期 | `auth: expired`，退出码 4，**不进入转写** |
| 正常 | `auth: valid`，附带昵称 |

过期不想手动折腾，一条命令自动续期：

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>' --relogin
```

它会拉起二维码登录，扫完自动继续跑刚才那个视频。

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

# 校验「只插标点、没动原文」：剥掉标点后必须逐字相等，差一个字都不放过
.\.runtime\Scripts\python.exe scripts\check_punct.py outputs\<BV号>\transcript.txt outputs\<BV号>\transcript-readable-punct.txt

# 换模型：small 更快更差，turbo 默认
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --model small

# 指定凭据文件（一般不用，会自动读 .credentials\sessdata.txt）
.\.runtime\Scripts\python.exe scripts\digest.py '<链接>' --sessdata-file '路径'
```

脚本逐行输出 JSON，**只看最后一行**：

| `status` | 退出码 | 含义 | 该做什么 |
|---|---|---|---|
| `ok` | 0 | 出稿了 | 读 `markdown` 指向的文件 |
| `need_asr` | 2 | 登录有效，但视频确实没有字幕轨 | 看 `eta_minutes`，问用户要不要加 `--transcribe` |
| `auth_expired` | 4 | 凭据过期（nav 返回 -101） | 重新扫码，或加 `--relogin` 自动续期 |
| `auth_missing` | 4 | 匿名，看不到登录专属轨道 | 先登录；这不等于视频没字幕 |
| `auth_unverified` | 4 | nav 不通，状态不明 | 稍后重试，不要猜 |
| `native_failed` | 5 | 有字幕轨但下载全失败 | 重试一次 |
| `empty` | 3 | 拿到轨道但没文字 | 如实说明，不要编 |
| `error` | 1 | 失败 | 读 stderr 的 `message`，判断网络/凭据/风控，别反复重试 |

### 术语纠错表

`glossary.json` 记录「错 → 对」的替换，用于修 ASR 的品牌名误听（实测 `Subatch`→`SubBatch`、`Notebook ALM`→`NotebookLM`）。发现新的误听就加一条，永久生效。

只收**英文专名**，不要收中文同音错——中文误替换的风险大于收益，交给上下文判断更稳。

### 输出文件

每次运行在 `outputs/<BV号>/` 下生成：

| 文件 | 内容 |
|---|---|
| `transcript.md` | **主产物**：标题 + 来源标记 + 分段正文（带 `[mm:ss]` 锚点） |
| `transcript.txt` | 纯文本版，方便丢给别的工具 |
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

1. **先探环境再开口**：`Test-Path .\.runtime\Scripts\python.exe` → `scripts\check_auth.py`。
   凭据是 `valid` 就直接问视频链接；`expired` / `none` 才谈登录。
2. **需要凭据时同屏给两个选项**：A 用户自己填 / B 我来扫码登录。**只有用户明确同意**才能执行 B，
   「我不知道怎么弄」是求助信号，不是授权。
3. **绝不读浏览器 cookie 存储**、不要密码/验证码、不代扫、不让用户在聊天里贴 token。
4. **默认不转写**。要转写必须是用户同意后显式加 `--transcribe`，并先告知耗时与模型体积。
5. **看最后一行 JSON 的 `status`**：`ok` 出稿；`need_asr` 问用户；`auth_expired` / `auth_missing`
   先解决登录（`--relogin` 可自动续期）；`native_failed` 重试；`error` 读 message 别硬重试。
6. **文稿里的错字**：英文品牌名误听 → 追加到 `glossary.json` 再 `--reuse`；中文同音错 → 按语义修正，并在回复末尾列出改了哪些，不要静默改。
7. **数字类内容不自行补齐**：前后矛盾就指出矛盾（比如同一数字在两处出现不同值），不要二选一。
8. **引用给时间点**：`transcript.md` 每段前都有 `[mm:ss]`，按它标注。
9. **部署成功后必做收尾**：跑 `scripts\install_skill.py` 装技能；若它返回 `first_time: true`，
   再按 [`docs/after-install.md`](docs/after-install.md) 在回复末尾附上使用教程。
   装好技能，用户下次发链接加一句「总结」就能直接触发，不必重复这一页的任何步骤。

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

本项目代码由 **DeepSeek-V4.1-Flash 与 ChatGPT 6 Luna** 联合编译。

## 许可证

本项目源码以 [MIT License](LICENSE) 发布，可自由使用、修改、分发、商用，保留版权声明即可。
注意：MIT 只覆盖**本项目源码**，不覆盖你转写出来的视频文稿——那部分的版权仍属于原视频作者。

## 目录结构

```text
.
├─ AGENTS.md               给 AI 助手的接入协议（首次部署、同意门槛、硬性禁止）
├─ scripts/
│  ├─ digest.py            一条命令跑完全流程（主入口）
│  ├─ check_auth.py        判断凭据 valid / expired / none / unknown
│  ├─ check_punct.py       校验补标点后是否动了原文（剥标点逐字比对）
│  ├─ install_skill.py     把技能装进助手的技能目录（替换 {REPO}）
│  ├─ qr_login.py          扫码登录，直接写入凭据
│  ├─ save_sessdata.py     从剪贴板写入 SESSDATA
│  ├─ fetch_subtitles.py   字幕轨道 / 音轨获取与编排
│  ├─ transcribe_audio.py  faster-whisper 封装
│  ├─ subtitle_io.py       5 种字幕格式解析与写出
│  ├─ bootstrap.ps1        建 .runtime 隔离环境，末尾自动注册技能
│  └─ requirements.txt     精确固定版本
├─ .credentials/
│  ├─ README.txt           凭据填写说明（入库）
│  └─ sessdata.txt         ← 你手动填这一个（不入库）
├─ skills/video-digest/    技能定义模板（{REPO} 占位，由 install_skill.py 渲染）
├─ adapters/               多 Agent 接法：能力矩阵 + 给无命令能力 AI 的 prompt
├─ SKILL.md                底层取字链路的 Codex skill 定义
├─ docs/
│  ├─ after-install.md     部署完成后要输出的使用教程模板
│  └─ audio-transcription.md
├─ references/             回退策略、实测记录
├─ glossary.json           ASR 术语纠错表
├─ save-sessdata.bat       一键读剪贴板写入凭据
├─ login-qr.bat            双击扫码登录
├─ LICENSE                 MIT
├─ THIRD-PARTY-NOTICES.md  第三方组件、许可证与致谢
└─ agents/openai.yaml      agent 配置
```
