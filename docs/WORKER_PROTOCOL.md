# Worker 协议 0.1.0（T03冻结候选，待成员复核）

范围：主编排独立Python环境，通过本地子进程 newline JSON-RPC 2.0 调用各软件worker。本版适配器不是MCP server；可由后续MCP桥接承接同样的job/result契约。不假定现有第三方MCP直接支持本协议。

## 配置与请求

worker.json 保存 `command`（参数数组，不通过shell）、`timeout_seconds`。每次请求启动一次小客户端/worker入口，该入口通过本机持久化job仓库连接长任务；不能因父进程退出杀死或重新提交已开始的计算。stdout仅返回一条JSON，诊断日志写本次run的文件。每次请求包含 jsonrpc="2.0"、id="request"、method、params；响应回显jsonrpc/id，结果放result。错误必须结构化保存在本机日志和job状态，客户端不回显可能含密钥的stderr。

支持：

- `workflow.submit`：params符合 contracts/job.schema.json。先检查approval/plan/input hash、工具schema/版本、许可、登记dataset和相对输出目录，再执行。持久化幂等键；同键同载荷返回原job；同键不同载荷拒绝。
- `run.status`：params为 job_id。返回 contracts/result.schema.json，可queued/running/succeeded/failed/cancelled/unknown。未知job不能自动当作未提交，须检查旧进程/产物后人工协调。当前客户端对未知/无效结果保持阻塞。
- `run.cancel`：params为 job_id。停止本job的执行/排队并持久化终态，保留已产出证据。不杀用户其他进程；取消无法确认则返回不确定状态，协调器不会宣布取消成功。

## Worker必须落地的约束

1. 真实软件环境/许可由本机探测。Pro专用Python、ENVI/IDL、MATLAB分别隔离，按实际版本调用，不静默替换原生算法。
2. 解析dataset ID只能访问input manifest登记文件；原件只读；不能采信模型传来的任意路径。输出只写独立run的 artifacts/step_id（本协议首版约定），必要中间产物写work/step_id，不覆盖旧未知文件。
3. 冻结plan/approval记录可由worker通过受信本地协调器查询；必须复验而不是只检查approval_id非空。worker还须绑定本次run_root配置，不能自行推断用户盘符。
4. software_lock/project_lock/desktop_lock携带owner、run_id、PID、心跳和到期。过期先核对旧进程与产物，不能自动接管。截图和计算分队列；本版只有单协调器，跨CLI同一runtime的内核锁互斥。
5. 长任务submit尽快返回job；本地持久进程继续工作，后续status查询。API超时/客户端退出不授权再算。协调器在提交前已持久化dispatch_intent；恢复只查原job。
6. 返回effective_parameters（不得漏默认实际值；若原生展开默认值与计划不同，计划应事先写清规范化有效参数）、真实software/version、input hash、实现性质、文件sha256/size、check IDs及告警。协调器发现不一致会阻断；软件成功退出本身不代表成功。
7. 所有必需step产物、最终交付kind和需求acceptance_check IDs通过才Completed；本版hash/格式/引用校验不能替代T17/T22独立科学检查。独立检查器的结果须由本机worker收集并使用计划中的check IDs。

## 截图与报告

artifact.kind=screenshot必须携带capture结构：软件/版本、真实窗口标题/PID、图层/文件、capture时间、所展示artifact ID及哈希、identity_check、操作/结果展示类型。时间不得早于本run，引用必须属于本run。首版接受PNG；magic header仅作基本格式检查，实际可读性和窗口身份还需T16检查/人审。禁止将地图导出图冒充窗口操作证据。

DOCX核查ZIP结构，PDF核查内容签名；完整页数、中文字体、版式、图表一致性由T23及独立评审负责。对于正式实验，plan.required_deliverables应包含data、project或reproducible_package、screenshot、docx、pdf；本版不代替用户选择交付范围。

## 失败与恢复

默认不自动重试有副作用步骤。已确认失败的新尝试需解释修复依据并新revision/确认，保留旧run。上限为一轮同错误修复，额外请求按预算与范围处理。响应丢失先status，原结果有证据可直接复用，unknown阻塞。取消/暂停保留所有事件。尚未实现的worker能力不得以mock或历史记录签验。
