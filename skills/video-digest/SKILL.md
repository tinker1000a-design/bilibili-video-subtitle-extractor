---
name: video-digest
description: 从视频链接自动提取字幕并分析内容。用户发来 B 站（或 yt-dlp 支持的站点）视频链接、并想了解这个视频讲了什么时使用。原生字幕优先，取不到时自动本地语音转写，然后输出可读文稿与内容分析。触发词：分析这个视频、这个视频讲什么、帮我看看这个视频、提取字幕、视频总结、视频笔记。
---

# 视频转文稿与内容分析

把视频链接变成「可读文稿 + 内容分析」。默认一条命令跑完全流程，不要拆成多步问用户。

## 使用前：确定仓库位置

下文的 `{REPO}` 指**本 skill 文件所在仓库的根目录**（即 `scripts/digest.py` 的上级目录）。
装到 AI 助手的技能目录时，把 `{REPO}` 替换成实际绝对路径，例如：

- 本机：`E:\_ai_agent\video-subtitle-fetcher`
- 其他机器：你 clone 到的地方

首次使用前确认 `.runtime` 存在；不存在就先跑 `{REPO}\scripts\bootstrap.ps1`，详见仓库 README。

## 一条命令

```powershell
& '{REPO}\.runtime\Scripts\python.exe' '{REPO}\scripts\digest.py' '<视频链接>'
```

常用变体：

```powershell
# 只探有没有现成字幕，不转写（秒回）
... digest.py '<链接>' --no-asr

# 换模型（small 更快更差，turbo 默认）
... digest.py '<链接>' --model small

# 已有结果时重新生成文稿（调完术语表后用，不重跑转写）
... digest.py '<链接>' --reuse

# 明确指定登录凭据（一般不用，会自动读 {REPO}\.credentials\sessdata.txt）
... digest.py '<链接>' --sessdata-file '路径'
```

脚本逐行输出 JSON。**只看最后一行**，它的 `status` 决定下一步。

**登录态是质量的分水岭（2026-10-17 实测）**：`.credentials\sessdata.txt` 填好后，首行 JSON 的 `auth` 为 `sessdata`，
B 站 AI 字幕轨可直接读取（`method: native-auto-caption`，`player/wbi/v2` 带登录态裸调可通，无需 wbi 签名）。
同一视频实测：有登录态 **1.5 秒**出稿且零错字；无登录态走 ASR **603 秒**且 3.46% 简繁混用、专名 7 种写法。
所以：**发现 `auth` 为 `anonymous` 时，先提醒用户填 SESSDATA，不要直接开 ASR 干等 10 分钟。**

### 需要凭据时：必须同时给两个选项

不要把手动方案当成唯一出路。**同屏给出这两条**，让用户自己选：

- **A｜自己填**：`F12` → 应用/Application → Cookies → `https://www.bilibili.com` → 筛 `sess` → 右键 SESSDATA → 复制值 → 粘到 `{REPO}\.credentials\sessdata.txt`，或双击 `{REPO}\save-sessdata.bat` 从剪贴板写入
- **B｜扫码登录（我来做）**：跑 `& '{REPO}\.runtime\Scripts\python.exe' '{REPO}\scripts\qr_login.py'`，生成 `{REPO}\.credentials\login_qr.png`，让用户用手机 B 站 App 扫码并在手机上点确认；成功后自动写入凭据并打印 `{"status":"ok"}`

**B 需要用户明确同意才能执行**（「可以 / 你来 / 自动 / 帮我弄」这类肯定答复）。
「我不知道怎么弄」「太麻烦了」**不是同意**，那是求助信号——把 A 和 B 讲清楚，等他选。沉默、只发链接、换话题都不算同意。

执行 B 之前先讲清三件事：首次会下载依赖（约 1 分钟；若走 ASR 还要下 1.6GB 模型）、账号会新增一条登录设备记录（可在 App 里移除）、凭据写入被 `.gitignore` 排除的 `.credentials\sessdata.txt`。

`qr_login.py` 会阻塞等待扫码，操作顺序是：先读到 `{"status":"qr"}` 那一行 → 把 PNG 展示给用户 → 再等任务结束。
`waiting_confirm` 表示用户扫了但没在手机上点确认，提醒他一下；`expired` 就重跑一次，**不要连续重试超过 2 次**。

**二维码寿命约 3 分钟**（实测 182 秒被 B 站判过期），所以生成前先问一句「手机在手边吗」——
对着一个已经作废的码等人回头，是最常见的失败原因。默认 `--retries 0` 是刻意的：自动换码会覆盖
用户正在看的那张图，而他的查看器不会自动刷新。


| status | 含义 | 你该做什么 |
|---|---|---|
| `ok` | 完成 | 读 `markdown` 路径的文件，进入分析 |
| `need_asr` | 探测阶段判定要转写（此时命令仍在继续跑，除非加了 `--no-asr`） | 已带 `eta_minutes`，可以先告诉用户预计耗时 |
| `need_asr` + `--no-asr` | 没有现成字幕 | 问用户要不要花时间转写 |
| `empty` | 拿到轨道但没文字 | 如实说明，不要编 |
| `error` | 失败 | 读 stderr 的 message，判断是网络、凭据还是风控，不要反复重试 |

`method` 字段是质量的分水岭，必须写进结论：
- `native-caption` / `native-auto-caption`：站点字幕轨道，质量高，可当原文引用
- `speech-recognition`：本地识别，已做简繁统一，但**专名、数字、同音词可能出错**

## 分析规范

默认按下面的结构输出，**用直白口语，不要堆术语和标题层级**：

1. **一句话主旨** —— 这视频到底在讲什么，一句说完
2. **讲了哪几件事** —— 3~6 条，每条一两句，按视频原本的顺序
3. **作者自己的判断** —— 哪些是他本人的观点，不是复述事实。这部分最有价值
4. **值得记的数字或结论** —— 挑 2~4 个
5. **可信度提示** —— 如果 `method` 是 `speech-recognition`，一句话说明哪些地方可能听错

用户要求"详细/深入/拆解"时再展开：加时间戳锚点、论证链、质疑点、延伸阅读。

**不要做的事**：

- 不要用视频原文没说的背景知识去补充成"视频里讲了"
- 不要把 ASR 的错字照抄进分析（能从上下文判断的按原意写，判断不了的标注存疑）
- 不要一开始就输出长表格和四级标题，先把话说明白

## 质量纪律

- 引用具体说法时，能定位就给时间点（`[mm:ss]`），transcript.md 里每段前面都有
- ASR 文稿里的专名如果是明显的同音错，按语义修正，但**在末尾集中列出你改了哪些**，让用户能回听核对
- 数字类内容不自行推算补齐；前后矛盾就指出矛盾，不要二选一
- 品牌名/英文专名是 ASR 的高频错误区（实测 Subatch→SubBatch、Notebook ALM→NotebookLM）。发现新的误听，**追加到 `{REPO}\glossary.json`**（键=错、值=对），下次自动生效；中文同音错不要往表里加，避免误替换

## 边界

- **不读浏览器 Cookie。** 不碰 Chrome / Edge / Firefox 的 Cookies 数据库，不用 DPAPI 解密，不用任何「自动提取 cookie」的库。需要登录态只有两条路：用户自己填，或用户明确同意后走 `qr_login.py` 扫码。理由不只是技术上 Chrome 127+ 的 App-Bound Encryption 会失败，更是因为读凭据存储属于越权行为
- 不索要账号密码或短信验证码；不让用户在聊天里贴 token（贴了就提醒他这是登录态，建议退出所有设备重登）
- 不绕过登录/付费/DRM；二维码必须用户本人扫，不得代扫或代确认
- 只处理单个视频，不静默遍历播放列表；合集需逐个给链接
- 拿不到字幕、也转写不出有效语音时，如实报告阻碍，不用猜的内容填空
- 输出文件保存在 `{REPO}\outputs\<BV号>\`（`transcript.md` / `transcript.txt` / `probe\subtitles.srt`）

## 环境

- 运行时与模型都在 `{REPO}` 下（`.runtime` 隔离环境，`.models` 模型缓存约 1.6G）
- 首次或依赖缺失时执行 `{REPO}\scripts\bootstrap.ps1`（需要 uv；ffmpeg 只在走 ASR 时必需）
- 速度为 CPU int8 下约 2.9 倍实时，30 分钟视频约 10 分钟转写；模型已缓存后不再下载
- 原生字幕路径与视频长短无关，固定 1-2 秒；ASR 只在确实没有字幕轨时才启动
- SESSDATA 有效期约 3 个月，失效表现为 `auth` 回到 `anonymous`，重新填 `.credentials\sessdata.txt` 即可
