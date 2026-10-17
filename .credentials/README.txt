# SESSDATA 获取与填写方法

## 两条路，选一条

### 路 B：扫码登录（推荐，不用开开发者工具）

直接双击项目根目录下的：

    login-qr.bat

或者命令行：

    .\.runtime\Scripts\python.exe scripts\qr_login.py --open-image

然后：手机 B 站 App 扫屏幕上弹出的二维码 → 手机上点确认 → 脚本自动写入本目录的 sessdata.txt，
打印 {"status":"ok"} 就完事。全程不需要 F12，也不需要复制任何东西。

说明：走的是 B 站官方扫码登录接口，不读浏览器 Cookie、不要密码、不要验证码。
代价是账号会多一条登录设备记录，不想要了在 App「登录设备管理」里移除即可。

### 路 A：手动复制（想知道原理，或扫码失败时用）

## 这个文件在哪

    <项目根目录>\.credentials\sessdata.txt

（就是本说明文件所在的目录）

## 填什么

B 站登录 Cookie 里名为 SESSDATA 的那一项的值，形如：

    xxxxxxxx%2C1790000000%2Cxxxxx%2Axx

特征：含 %2C，长度一般 30-40 字符，不含空格、不含 http。

## 怎么拿（只用面板法——SESSDATA 是 HttpOnly，JS 读不到）

已实测：B 站的 SESSDATA 带 HttpOnly 标记，document.cookie 里根本不存在，
所以任何 Console 里的 JS 写法都会报 Cannot read properties of undefined。
这是浏览器的安全设计，不是脚本问题。

正确做法：
1. 浏览器登录 bilibili.com，随便打开一个视频页
2. F12 → 顶部选「应用 / Application」
3. 左侧「存储」→ Cookies → https://www.bilibili.com
4. 上方筛选框输入 sess
5. 右键 SESSDATA 那一行 → 复制 → 复制值（Copy value）
   ⚠ 屏幕上显示的值是截断的（形如 1a2b3c4d%2C...），必须用右键菜单复制，不要用鼠标拖选

备选：Network 面板 → 刷新页面 → 点任意请求 → Headers → Request Headers 里的 cookie: 整条复制，
本工具也支持整条 cookie（会自动剥出 SESSDATA）。

## 怎么填（二选一）

方式 A（一键，推荐）：

    双击 <项目根目录>\save-sessdata.bat
    → 回车 → 脚本自己从剪贴板取 token 写入文件

方式 B（手动）：

    右键 sessdata.txt → 打开方式 → 记事本
    粘贴 token → Ctrl+S 保存 → 关闭
    只放这一串，不要加引号、不要加说明文字、不要换行分段

## 怎么确认生效

    .\.runtime\Scripts\python.exe scripts\check_auth.py

- {"auth": "valid", "uname": "你的昵称", "action": "ready"} → 成功
- {"auth": "expired", "action": "login_required"} → 文件里有值，但 B 站判定未登录（已过期或被撤销）
- {"auth": "none", "action": "login_required"} → 文件不存在 / 为空 / 解析不出

保存前检查格式并通过 nav 验证；验证失败时保留旧文件，不回显剪贴板内容。文件使用临时文件原子替换。凭据优先级是显式文件 > BILI_SESSDATA 环境变量 > 默认文件。

为什么不能只看视频接口：player 接口对「凭据过期」和「视频没字幕」返回一模一样的结果，
所以必须用 check_auth.py 单独确认。过期了直接双击 login-qr.bat 重新扫一次即可。

## 注意

- 这串东西等于你的账号登录态，拿到它的人可以操作你的账号。不要发给任何人、不要提交到 git。
- 有效期以 Cookie 的 Expires 为准（实测常见 3 个月左右，不是无限期）。失效后 auth 为 expired；重新扫码或用面板复制一次即可。
- 本目录已写入 .gitignore，不会被提交；只有本说明文件例外。
