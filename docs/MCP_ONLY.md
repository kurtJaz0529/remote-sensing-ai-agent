# MCP 接入约定

最新真实MCP运行：`RUN-1999fb16a1ab47c4bfceeb659e3c28c1`，Completed，三步均succeeded、原件不变。冻结计划哈希 `4d60a347d40a1d0c6f7f2eb18016b67eb7a2231da9bc3bd43d9f4756e14ceeeb`，公开结果见 `evidence/native-integration/mcp-integration-summary.json`。76项测试0失败/错误、1项Windows符号链接权限跳过；MCP握手/工具发现/提交/跨会话查询/重复提交/取消终态测试通过。

用户最新要求：三软件均采用 MCP 接入，禁止 Computer Use。软件调用、状态与取消通过 MCP 工具执行；ENVI Classic 由专用 MCP 启动、验证窗口身份、调用真实菜单并抓取原始截图。通用 Computer Use 入口保持停用。

链路：协调器 → MCP `workflow_submit/run_status/run_cancel` → 持久任务仓库与worker → 固定软件适配器 → 本机 ENVI/ArcPy/MATLAB。底层软件专用Python或MATLAB进程是MCP服务的实现，不是桌面自动化。各软件原有MCP仍可承担发现/参数查询，正式编排的确认、幂等和证据统一由本服务检查。

安装：`python -m pip install '.[mcp]'`。固定 MCP Python SDK 1.28.1。

运行持久服务：

```powershell
python -m orchestrator.mcp_server --root <runtime绝对路径> --http --port 8765
```

服务仅绑定 `127.0.0.1`，Streamable HTTP MCP 地址为 `http://127.0.0.1:8765/mcp`。本项目 `McpWorker` 使用SDK执行握手、工具调用与结构化结果解析，超时/错误不自动重试提交。`scripts.run_native_workflow` 会为验证启动独立本地MCP服务，完成时关闭；在途/不确定任务保留服务与端点文件以供原job查询。

stdio入口仍可启动供工具发现、状态和取消；异步submit明确拒绝。原因是官方SDK的Windows stdio实现给服务端及子进程附加生命周期Job Object，客户端断开时会清理后代，不能保证长任务存续。HTTP服务独立于单次MCP连接，其后端runner不会因客户端断开而被清理。该行为已有实际失败复现与HTTP回归测试，不通过修改SDK或绕过系统安全设置解决。

本轮用户补充要求前曾尝试通过 Computer Use 检查 ArcGIS 窗口，没有取得截图成果；要求生效后已停止该入口。ENVI Classic 专用 MCP 已得到三张未编辑的诊断截图，冻结计划和窗口/进程/时间/文件哈希齐全，见最新批次证据。其 diagnostic 模式完整性只覆盖该三步探针，不能作为完整实验报告门通过的证明。MATLAB/ArcGIS 的真实窗口截图要求仍待完成；软件图像导出须单独标注。

已验证能力还包括登记 Canon City 的原生分类诊断、用户第二幅 RGB 影像的裁剪读取，以及批准计划绑定的 PNG 文件完整性审计。统一 MCP 服务现有四个工具：workflow_submit、run_status、run_cancel、registered_input_audit。固定 provider 探针另通过受限 MCP 进程执行，密钥仅经明确的进程环境变量传递，工具提议不执行。整个 32 项计划仍按各项科学验收条件推进。
