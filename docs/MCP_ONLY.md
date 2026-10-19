# MCP 接入约定

最新真实MCP运行：`RUN-1999fb16a1ab47c4bfceeb659e3c28c1`，Completed，三步均succeeded、原件不变。冻结计划哈希 `4d60a347d40a1d0c6f7f2eb18016b67eb7a2231da9bc3bd43d9f4756e14ceeeb`，公开结果见 `evidence/native-integration/mcp-integration-summary.json`。76项测试0失败/错误、1项Windows符号链接权限跳过；MCP握手/工具发现/提交/跨会话查询/重复提交/取消终态测试通过。

用户最新要求：三软件均采用 MCP 接入，禁止 Computer Use。后续软件调用、状态与取消通过本服务 MCP 工具执行；不使用桌面点击、按键或 Computer Use 截图。

链路：协调器 → MCP `workflow_submit/run_status/run_cancel` → 持久任务仓库与worker → 固定软件适配器 → 本机 ENVI/ArcPy/MATLAB。底层软件专用Python或MATLAB进程是MCP服务的实现，不是桌面自动化。各软件原有MCP仍可承担发现/参数查询，正式编排的确认、幂等和证据统一由本服务检查。

安装：`python -m pip install '.[mcp]'`。固定 MCP Python SDK 1.28.1。

运行持久服务：

```powershell
python -m orchestrator.mcp_server --root <runtime绝对路径> --http --port 8765
```

服务仅绑定 `127.0.0.1`，Streamable HTTP MCP 地址为 `http://127.0.0.1:8765/mcp`。本项目 `McpWorker` 使用SDK执行握手、工具调用与结构化结果解析，超时/错误不自动重试提交。`scripts.run_native_workflow` 会为验证启动独立本地MCP服务，完成时关闭；在途/不确定任务保留服务与端点文件以供原job查询。

stdio入口仍可启动供工具发现、状态和取消；异步submit明确拒绝。原因是官方SDK的Windows stdio实现给服务端及子进程附加生命周期Job Object，客户端断开时会清理后代，不能保证长任务存续。HTTP服务独立于单次MCP连接，其后端runner不会因客户端断开而被清理。该行为已有实际失败复现与HTTP回归测试，不通过修改SDK或绕过系统安全设置解决。

本轮用户补充要求前曾尝试通过Computer Use启动和检查ArcGIS窗口，没有取得截图或操作成果；要求生效后已停止该入口。T16后续必须由软件MCP自身提供真实截图/窗口身份能力；若工具只能导出图像，必须标记为图像导出，不能冒充窗口截图。当前T16截图要求仍未验收。

能力仅限登记Canon City案例最小处理验证，配置/代码/输入哈希绑定确认；不是通用分类能力。整个32项计划不因MCP接入完成而自动完成。
