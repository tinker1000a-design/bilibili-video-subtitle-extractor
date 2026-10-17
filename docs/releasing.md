# 发布与验收

目前面向 Windows 10/11、Python 3.12。本次增加的 Ubuntu CI 验证离线代码和依赖；Windows 批处理与 PowerShell 入口仍是部署主路径。

## 固定依赖

`scripts/requirements.txt` 维护直接依赖；`scripts/requirements.lock` 固定完整依赖树、环境条件与制品哈希。部署使用 `uv pip sync --require-hashes`，CI 用 `pip install --require-hashes`，不在运行时自动升级。

调整直接依赖后重新生成并审阅锁文件：

```powershell
uv pip compile scripts/requirements.txt --python-version 3.12 --universal --generate-hashes --output-file scripts/requirements.lock
```

## 每次发布必须完成

1. 在新的 Python 3.12 环境从锁文件安装；检查依赖一致性和全部运行时导入，不实例化模型。
2. Windows、Ubuntu 的 GitHub Actions 离线回归均通过。测试使用临时目录，网络请求默认禁止，不读取真实凭据、不下载模型。
3. 审阅变更，确认没有凭据、输出文稿、音视频或模型进入提交。
4. 用有授权的账号和单个视频另做人工验收：扫码成功/过期、有效凭据获取字幕、无字幕时先停止、明确同意后的 ASR。记录提交、系统、来源与耗时。不能将替身测试写成真实站点实测。
5. 仅对已经通过上述验收的明确提交创建版本标签与 Release；说明已测范围、已知限制和兼容变化。不因补齐发布流程而自动发布。

## 本次兼容变化

- 标点检查改为只插入允许的语句标点与空白；原有字符和符号必须保留。检查不证明断句语义正确。
- 默认字幕查询不转写；`--no-asr` 与 `--transcribe` 互斥。
- 统一凭据优先级：显式文件 > 环境变量 > 默认文件。凭据写入需格式和登录验证，失败保留旧文件。
- 技能安装遇到冲突不写入。旧版无安装标记的副本需在核对目标后用 `--target ... --replace-existing` 迁移；每次替换独立备份。
- 缓存记录本次成功来源及 URL 别名。历史缓存没有来源指针时优先原生字幕。无法确认身份的缓存拒绝复用。

自动测试入口：`python -m unittest discover -s tests -v`。`test_audit_regressions.py` 保留可对照审计版本运行的缺陷反例；`test_safety_boundaries.py` 覆盖失败与边界；`test_cli.py` 包含真实子进程调用和不加载模型的 ASR 身份字段检查。
