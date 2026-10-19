# 云端成果导入记录

2026-10-19 从 Notion 的 T03《本地目录、协议与Notion协作初始化》附件取得云端 Codex 交付。

| 原始文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| rsagent-cloud-core-0.1.0-dev1.zip | 168466 | a8610d1be4d0b2d1c5c71d435f19f832051ae39c0cfc08eb3e5dd7210f3a5f6b |
| rsagent-release-manifest-0.1.0.json | 16455 | be3bc864d6ff85dce8743c9ec50ae05c7957cefc7cf1f49ccc2006bec1123a4e |

导入前已逐项校验清单中的 95 个文件；全部大小与 SHA-256 匹配。第一个 Git 提交保存原始源码结构，后续提交单独记录协作更新与本机修复。原包还包含清单本身，共 96 个文件。

`releases/release_manifest.json`、wheel、`evidence/clean-install/` 和 `evidence/mock-demo/` 均为云端交付的历史产物。原始测试结论为 Linux / Python 3.12 的 51 项单元/mock/协议测试通过及 14 个 Schema 示例通过；这不是用户 Windows 或真实软件的验收记录。

原始 manifest 固定原包内容，不能用来验证后续修改后的工作树。需要复核原包时，将原始 ZIP 解压到独立目录后运行原 `scripts/verify_release.py`；当前源码以 Git commit 标识，任何新 release 应重新构建 wheel 并生成新清单。仓库内原 wheel 不包含后续 Git 修改。

## 本机导入验证

首次在 Windows / Python 3.13 复跑 51 项测试：49 项通过，2 项在临时目录清理时报 WinError 32。原因是测试通过 unittest.addCleanup 注册 SQLite 关闭，但临时目录的 with 块先退出，连接尚未关闭。修复使用 contextlib.closing，确保清理目录前释放连接，未改变经验晋级算法。

最终本机复跑结果记录在 `evidence/windows-import/summary.json`。三软件连接、真实模型 API、实际遥感数据处理、真实截图、报告与保留案例验收分别仍待实施；核心测试通过不会推进这些任务为完成。

公开导入前已检查源码和 wheel 中的常见凭据模式；不导入 Notion 签名下载地址或个人实验原件。specs/ 保存历史计划，后续协作方式以 docs/COLLABORATION.md 和用户最新要求为准。
