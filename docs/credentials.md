# 凭据（SESSDATA）细节

README 只留了最短路径，这里是完整版。两种情况需要看：手动复制那一步卡住了，或者凭据验证结果看不懂。

## 一、为什么只有 SESSDATA

B 站字幕接口对匿名用户的返回是「空列表」，而**过期凭据返回的也是一模一样的空列表**。所以只看字幕接口，永远分不清「这个视频没有字幕」和「你的凭据过期了」。

因此本工具先用 `nav` 接口单独核验登录状态（`code=0` + `isLogin=true` 才是 valid），再决定是否去取字幕。这个判断逻辑在 `scripts/check_auth.py`。

只需要 SESSDATA 一个值，其他 cookie（`buvid3`、`bili_jct` 等）对本项目无用。

## 二、手动复制（方案 B）逐步

`SESSDATA` 带 `HttpOnly` 标记，**JS 读不到**，`document.cookie` 里根本不存在。任何在控制台敲 `copy(document.cookie)` 的写法都必然报 `Cannot read properties of undefined`。

只能用开发者面板：

1. 浏览器登录 `bilibili.com`，随便打开一个视频页
2. `F12` → 顶部选「**应用 / Application**」
3. 左侧「存储」→ **Cookies** → `https://www.bilibili.com`
4. 上方筛选框输入 `sess`，列表只剩一行
5. **右键点击 `SESSDATA` 那一行 → 复制 → 复制值（Copy value）**

> ⚠️ 屏幕上显示的值是**截断的**（形如 `1a2b3c4d%2C...`），用鼠标拖选只能拿到前 8 位。**必须走右键菜单。**

备选路线：`F12` → **Network** → 刷新页面 → 点任意请求 → Headers → Request Headers → 整条 `cookie:` 复制。本工具支持整条 cookie，会自动剥出 SESSDATA。

Firefox 的叫法略有不同：`F12` → 「存储」标签 → Cookies。

## 三、粘进去的格式

文件：`<项目根目录>\.credentials\sessdata.txt`

内容只有那一串，形如：

```
xxxxxxxx%2C1790000000%2Cxxxxx%2Axx
```

判别标准：**含 `%2C`**，长度一般 30-40 字符（也可能到 200+），不含空格，不含 `http`。

三种写法都能被识别；格式检查不证明凭据有效，保存前还会联网验证，失败时保留旧文件且不回显剪贴板：

| 你粘进去的 | 结果 |
|---|---|
| `xxxxxxxx%2C...`（裸 token） | ✅ 直接用 |
| `SESSDATA=xxxxxxxx%2C...` | ✅ 自动剥出值 |
| `buvid3=AAA; SESSDATA=xxx; bili_jct=yyy`（整条 cookie） | ✅ 自动剥出值 |
| 视频网址 | ❌ 明确报错，不会静默失败 |

## 四、一键写入（不开记事本）

复制好 token 后，双击项目根目录的 `save-sessdata.bat`。按任意键 → 脚本从剪贴板取、剥值、写进 `.credentials\sessdata.txt`，打印打码后的结果供核对：

```
[OK] saved to ...\.credentials\sessdata.txt
     token: 7686...a1b2  (222 chars)
     format looks correct (contains %2C)
```

好处是 token 直接从剪贴板进文件，**不经过聊天窗口、不经过命令行参数**（不会留在 shell 历史里）。

## 五、验证输出逐条解释

```powershell
.\.runtime\Scripts\python.exe scripts\check_auth.py
```

| 输出 | 含义 | 怎么办 |
|---|---|---|
| `{"auth":"valid","uname":"昵称","action":"ready"}` | 真的生效了 | 正常用 |
| `{"auth":"expired","action":"login_required"}` | 文件里有值，B 站判定未登录 → 过期或被撤销 | 重新扫码，或 `--relogin` |
| `{"auth":"none","action":"login_required"}` | 文件不存在 / 为空 / 解析不出 | 按上面第一到三节填 |
| `{"auth":"unknown","action":"retry_later"}` | 网络不通，状态不明 | 稍后重试，别急着换凭据 |

## 六、过期与续期

B 站发的 SESSDATA 有效期一般 **3 个月**左右（可在 DevTools 的 Expires 列看到）。

以前过期是静默的：接口只返回空字幕列表，和「这个视频没有字幕」长得一模一样，工具就误以为没字幕，白跑一次转写。现在会先问 `nav` 接口，所以能直接说清是哪种：

| 情况 | 现在的表现 |
|---|---|
| 没有文件 / 文件空 | `auth: none`，提示去登录 |
| 有值但过期 | `auth: expired`，退出码 4，**不进入转写** |
| 正常 | `auth: valid`，附带昵称 |

不想手动折腾，一条命令自动续期并接着跑：

```powershell
.\.runtime\Scripts\python.exe scripts\digest.py '<视频链接>' --relogin
```

## 七、二维码那点事

- 走 B 站官方扫码登录接口，**不读浏览器 Cookie、不要密码、不要验证码**。
- 代价是账号会多一条登录设备记录，不想要了在 App 里随时移除。
- 二维码实测**约 182 秒**过期，这是 B 站服务端的限制，不是脚本设的 `--timeout`。
- `--retries` 默认 0：自动换码会覆盖同一张 PNG，而你看的那张图不会刷新，反而更乱。过期就重跑一次。
- 换机器或换账号时，删掉 `.credentials/sessdata.txt` 重扫即可。
