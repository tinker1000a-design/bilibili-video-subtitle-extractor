# SESSDATA 获取与填写方法

## 这个文件在哪
    E:\_ai_agent\video-subtitle-fetcher\.credentials\sessdata.txt

## 填什么
B 站登录 Cookie 里名为 SESSDATA 的那一项的值，形如：
    xxxxxxxx%2C1790000000%2Cxxxxx%2Axx
特征：含 %2C，长度一般 30-40 字符，不含空格、不含 http。

## 怎么拿（只用面板法——SESSDATA 是 HttpOnly，JS 读不到）
已实测：B 站的 SESSDATA 带 HttpOnly 标记，document.cookie 里根本不存在，
所以任何 Console 里的 JS 写法都会报 Cannot read properties of undefined。这是浏览器的安全设计，不是脚本问题。

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
    双击 E:\_ai_agent\video-subtitle-fetcher\save-sessdata.bat
    → 回车 → 脚本自己从剪贴板取 token 写入文件

方式 B（手动）：
    右键 sessdata.txt → 打开方式 → 记事本
    粘贴 token → Ctrl+S 保存 → 关闭
    只放这一串，不要加引号、不要加说明文字、不要换行分段

## 怎么确认生效
跑任意视频，输出第一行 JSON 里出现 "auth": "sessdata" 即成功；
如果是 "anonymous"，说明文件为空或格式不对。

## 注意
- 这串东西等于你的账号登录态，拿到它的人可以操作你的账号。不要发给任何人、不要提交到 git。
- 有效期通常半个月到一个月，失效后会自动退化成匿名（auth 变 anonymous），重新复制一次即可。
- 本目录已写入 .gitignore，不会被提交。
