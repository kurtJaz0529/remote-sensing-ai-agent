# 三成员交接

先读README、COLLABORATION、COVERAGE、WORKER_PROTOCOL，再看contracts/、examples/与specs/原文快照。Notion任务汇总继续更新同一编号；根据用户2026-10-19的新要求，代码及公共文件在GitHub协作。本地Codex与Antigravity继续开发，云端Codex后续承接补充工作。源码已导入本仓库，跨环境不依赖云端工作区路径。

## 本地 Codex 接手

1. 完成T01/T02，提交environment、capabilities、input_manifest、原件哈希与缺项。
2. 按contracts/job/result实现T08持久化worker，检查确认记录、工具参数、登记输入和输出目录；实现真实软件/工程/桌面锁、取消与版本隔离。先使用本包MockWorker比对协议，再逐软件联调。既有MATLAB官方MCP的复用不必重写，但须桥接并固定版本。
3. 每个宣称available的工具提供本机真实run ID、参数schema、工具版本与实现性质，产出capabilities.json。把其规范化指纹冻结进计划再确认；代码变更/许可变化重新验证。
4. 在Windows独立CLI环境安装wheel，先重跑协议demo，再做最小软件读→处理→保存→重读。真实截图必须T16取证。worker的输入只读与锁无法在当前云端替你验证。
5. 真实API小请求在已配置凭据的环境运行provider probe；仅将统计/状态同步Notion，不上传密钥。工具与视觉分别验证。

## Gemini（Antigravity）接手

按source/knowledge schema交T05/T06来源和卡片；未有本机验证条目保持candidate/not_run。填写明确软件版本/许可/产品/格式。方法和核验器应输出稳定check ID，由T07绑定到task.requirements.acceptance_checks。独立核验器由云端评审，真实软件由本地运行。

报告数据来自同一冻结run；kind字段与截图capture元数据遵循协议。补交真实要求文件和T07矩阵后，可验证当前文本提取与结构化导入是否覆盖要求。OCR/图片/公式模块尚无实现，不可默认已理解。T29正式题集放在执行知识库以外，保留验收答案不得导入检索。

## 待输入与不受影响部分

- T01/T02、T08、T05/T06/T07及T24证据尚未在汇总库中提供。已有文档快照是设计，不作为完成证据。
- 三软件安装/许可/桌面无法由云端代验。T25/T30终验等真实证据包和用户案例。
- 当前云端环境没有配置模型secret绑定；T04的真实API验收留待有配置的环境，不要求在Notion中提供密钥。
- 本批测试证据、源码、schema、运行说明可供成员立即并行接入；正式发布门保持关闭。

## 回退

保留本zip及release manifest，部署到新目录和新的CLI虚拟环境；不原地覆盖旧run。知识快照重建新SQLite，撤回条目保留历史但不返回默认执行。经验撤回只关闭新任务规则，已确认运行仍引用旧冻结版本。回退代码前先停止协调器并核对在途job；切换模型只切provider，不重建run或重提交已成功步骤。
