# 参与贡献与上传文件

本仓库公开可读。任何人都可以 Fork 后提交 Pull Request；直接 push 或通过 GitHub 网页 Upload files 写入本仓库，需要所有者授予对应 GitHub 账号写权限。Agent 不是单独的 GitHub 身份：本地 Codex 与 Antigravity 使用各自环境中已授权的账号。

## 开始工作

1. 阅读 README、AGENTS.md、docs/COLLABORATION.md 与相关 Notion 任务；确认任务编号、依赖及验收条件。
2. 外部贡献者先 Fork；已有写权限的成员可直接从最新 main 建任务分支。不要与另一个成员共写同一工作副本。
3. 分支建议为 `local/T08-worker`、`antigravity/T05-sources` 或 `contrib/<简短主题>`。分支名只是约定，尚未替任何成员自动创建或分配。
4. 只修改任务范围内文件，提交后发起 Pull Request，写明任务编号、产物、实际验证、未验证项与限制。
5. 经另一成员复核后合并，随后更新 Notion 原任务记录的批次摘要和 commit/PR 链接。不要用一个新 Issue 重复承诺已有任务已完成。

有写权限的成员可在 GitHub 切换到自己的任务分支，选择 **Add file → Upload files** 上传文件，再发起 Pull Request。仅上传已获公开授权的源码、方法卡、Skill、模板、配置示例或脱敏证据。

## 本地开发验证

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install ".[documents]"
.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

协议演示必须使用新的空目标目录：

```powershell
.venv\Scripts\python scripts/demo.py --destination ../rsagent-protocol-demo
```

上面只验证核心代码与 mock 协议。方法、软件、许可、截图与科学结论必须有真实本机证据；不要把通过 CI 写成三软件接入完成。

## 文件边界

- 可提交：自研源码、协议、公开来源链接及必要摘录、方法/Skill、测试、报告模板、脱敏运行摘要。
- 留在本地：用户影像/ROI、原始要求或个人报告、密钥、OAuth 文件、签名下载链接、软件安装包/许可、完整运行数据库和保留验收答案。
- 公开证据只含必要摘要；不能仅依赖 .gitignore，应在暂存和上传前人工核对内容与 Git diff。
- 引入第三方代码时保留其许可和来源，记录固定版本。仓库公开不代表商业软件、实验数据或所有第三方代码可自由再分发。

## 遥感验收

记录真实波段、单位/比例、CRS、网格、逐波段 NoData、样本来源与类别映射。未知信息保持未知；没有可靠坐标/尺度时不输出真实地表面积。诊断复评、参考 ROI 一致性、独立测试精度分别标注。API 运行、GUI 操作和结果展示截图分别说明。
