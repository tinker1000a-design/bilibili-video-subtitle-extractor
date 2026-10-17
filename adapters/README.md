# 多 Agent 适配说明

> 一句话：**能跑本地命令的 Agent 靠「技能目录 / AGENTS.md」自动接入；不能跑命令的（ChatGPT 网页、豆包、扣子）只能当「文稿总结器」，拿不到字幕。**

## 能力矩阵

| Agent | 接入方式 | 能否自动取字幕 | 现状 |
|---|---|---|---|
| **WorkBuddy** | `~/.workbuddy/skills/video-digest/` | ✅ 全自动 | 已实测 |
| **DeepSeek Harness (DSH)** | `~/.dsh/skills/video-digest/` | ✅ 全自动 | 格式同构，磁盘布局一致 |
| **Claude Code** | `~/.claude/skills/video-digest/` | ✅ 全自动 | 同上 |
| **Codex（CLI / 桌面）** | 仓库根 `AGENTS.md` | ✅ 全自动，需在仓库目录下工作 | 已实测 |
| **Cursor / opencode / Aider / Zed** | 仓库根 `AGENTS.md` | ✅ 全自动，需在仓库目录下工作 | 遵循 AGENTS.md 约定 |
| **任意终端里的通用 Agent** | 直接读 `AGENTS.md` | ✅ 全自动 | 同上 |
| **ChatGPT 网页 / 豆包 / 扣子（Coze）/ Kimi 网页** | 无文件系统、不能执行命令 | ❌ **拿不到字幕** | 只能用 [transcript-summarizer.md](transcript-summarizer.md) 总结你贴进去的文稿 |

**为什么没有「每家一个适配文件」**：这些工具读的不是各自的私有格式，而是两类公共约定——技能目录（`<name>/SKILL.md` + frontmatter）和 `AGENTS.md`。同一份 SKILL.md 能直接放进 WorkBuddy、DSH、Claude Code，是因为它们的格式本来就一样。为每家复制一份不仅没有技术收益，还会在仓库里制造五个会互相漂移的副本。

---

## 方式一：技能目录（首选，装一次永久生效）

```powershell
.\.runtime\Scripts\python.exe scripts\install_skill.py
```

自动探测机器上已存在的技能目录并写入，路径替换成本机绝对路径。不存在的工具不会造目录。

装好后，新窗口里发 `链接 + 总结` / `链接 + zj` / `总结视频内容` 就会自动命中。

手动指定目标（装到别处）：

```powershell
.\.runtime\Scripts\python.exe scripts\install_skill.py --target "D:\some\agent\skills"
```

查看当前安装状态：

```powershell
.\.runtime\Scripts\python.exe scripts\install_skill.py --check
```

## 方式二：AGENTS.md（没有技能目录的 Agent）

只要 Agent 会读仓库根的 `AGENTS.md`（Codex、Cursor、opencode、Aider、Zed 都遵循这个约定），把仓库打开到工作目录即可。它包含完整的接入协议：先探环境、两个选项、同意门槛、硬性禁止、部署后收尾。

如果那个 Agent 只读固定文件名（比如 `CLAUDE.md`），把 `AGENTS.md` 复制或软链过去即可，内容不用改。

## 方式三：纯 Prompt（不能执行命令的 Agent）

ChatGPT 网页、豆包、扣子这类工具**没有本地文件系统和命令执行能力**，无论怎么配置都拿不到字幕。它们唯一能做的是：你先把 `transcript.md` 的内容贴进去，让它按统一规范总结。

用 [transcript-summarizer.md](transcript-summarizer.md) 里那段 prompt，粘贴到自定义指令或会话开头即可。它会按本项目的分析结构输出，并遵守同样的纪律（不编造、标注识别存疑）。

---

## 想再往前一步：MCP

如果希望 ChatGPT 桌面版、扣子这类工具也能**直接取字幕**（而不是让你手动贴），唯一的路是把 `digest.py` 包成 MCP server，让它们通过网络调用。没有实现，原因是代价不成比例：

- 需要一个常驻进程 + 用户网络可达（本地跑则要隧道或内网穿透）
- ChatGPT 的 MCP 连接器要求服务端可公网访问，等于把「本地工具」变成「在线服务」，凭据保管方式要跟着改
- 这些工具的用户大多只需要「总结已经拿到的文稿」，性价比远低于直接用支持命令行的 Agent

真要做的话，入口在 `scripts/digest.py` 的 `main()`：它已经是「一行命令、一行 JSON 输出」的形态，包一层 stdio JSON-RPC 即可，主要工作量在参数映射和超时控制，不涉及改核心逻辑。
