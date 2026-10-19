# AI 遥感本地 Agent · Remote Sensing AI Agent

Windows 本地遥感实验 Agent：通过 DeepSeek/GPT 规划任务，调用本机 ENVI、MATLAB 和 ArcGIS Pro，保存可追溯的处理结果、真实截图、工程/复现包及报告。

**当前为 `0.1.0.dev3` 本地集成预览。三软件最小处理、ENVI 原生分类诊断与第二幅 RGB 影像读取均已通过 MCP 验证；ENVI Classic 有三张原始诊断截图，DeepSeek 工具与合成图视觉探针通过。完整实验报告、合格 ROI 和独立保留验收尚未完成。** 当前结果与任务边界见 [最新交付](docs/DIAGNOSTIC_INTEGRATION_20261019.md)，软件入口见 [MCP接入约定](docs/MCP_ONLY.md)。

本仓库由本地 Codex 与 Antigravity 持续协作，云端 Codex 后续承接补充开发或独立评审。欢迎其他贡献者通过 Fork / Pull Request 提交代码和文件；仓库写权限由所有者按 GitHub 账号授予。

- [贡献与文件上传](CONTRIBUTING.md)
- [成员分工、分支规则与 Antigravity 启动说明](docs/COLLABORATION.md)
- [32 项任务路线图](docs/ROADMAP.md)
- [导入来源与验证范围](docs/IMPORT.md)

首版只处理用户提供的数据，不建设影像搜索下载模块或产品 GUI。ENVI、MATLAB、ArcGIS Pro 需使用者自行安装并持有相应许可。

## 已交付的核心基线

基于 Notion《AI 遥感本地 Agent｜三成员协作与Notion任务计划 v1.1》。本包包含协议、模型接口、需求提取、计划确认、SQLite 编排、MCP worker、固定案例软件适配、候选方法和核验组件。当前发布物是开发预览，正式产品验收保持待完成。

## 安装

Python 3.11+，建议使用独立虚拟环境。原云端测试环境为 Linux / Python 3.12；本地导入已在 Windows / Python 3.13.7 通过 51 项核心测试与 14 个 Schema 示例。三软件环境仍需单独实测。

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install ".[mcp,science,documents]"
.venv\Scripts\rsagent doctor
.venv\Scripts\python -m unittest discover -s tests -v
```

Linux/macOS 可使用 `python -m venv .venv`，激活后执行 `python -m pip install '.[documents]'`。不需要将 ArcPy、MATLAB Engine、ENVI Python 依赖装进本环境。若安装 wheel，则 `python -m pip install 'releases/rsagent_cloud_core-0.1.0.dev1-py3-none-any.whl[documents]'`。

## 先重跑协议示例

```text
python scripts/demo.py --destination ../protocol-demo
```

示例自行创建一个明确标注 synthetic 的小文本输入，执行“未确认阻断→确认→mock写入→模拟响应丢失→恢复查询→完成”，生成事件、manifest 和摘要。它不做遥感计算，不生成软件截图，不证明科学方法或本机软件可用。重复运行请换一个空目标目录。

## 用户实验的入口

```text
rsagent init --input <用户目录> --dataset-id DATA-001 --output input_manifest.json
rsagent intake <要求.docx> --output extracted_requirements.json
rsagent --root <独立运行目录> plan --file plan.json --manifest input_manifest.json --input <用户目录>
rsagent --root <独立运行目录> approve TASK-001 --revision 1 --actor <确认人标识>
rsagent --root <独立运行目录> run TASK-001 --revision 1 --approval-id <上一步返回ID> --worker-config worker.json
rsagent --root <独立运行目录> status <run_id>
rsagent --root <独立运行目录> resume <run_id> --worker-config worker.json
rsagent --root <独立运行目录> export <run_id>
```

`plan.json` 需依据提取结果、实际文件与本机能力编写/复核；本版不将整份自然语言材料自动解释成完整科学方案。`intake` 提取 TXT/MD、DOCX 正文/表格、PDF 文本并保留位置；图片、公式、扫描件、附件与语义冲突须人工/后续组件核实。冲突/未知项写入 `conflicts` / `open_questions` 会阻止确认。产品运行时确认与本次开发授权不同；此CLI的 actor 是审计标签，依赖受信任的本机操作者，不是身份认证系统。

真实执行还需本地成员提供 `capabilities.json`、冻结其规范化JSON哈希至 `frozen_versions.capabilities_sha256`，以及遵循 [WORKER_PROTOCOL.md](docs/WORKER_PROTOCOL.md) 的本机worker。默认不启用任何真实软件能力。相同 approval 与 mode 重复 `run` 返回同一运行；有意重新实验应取得新的确认记录。

## 模型接口

复制 `examples/openai.provider.json` 或 `examples/deepseek.provider.json`，填入实际 endpoint/model；通过配置所命名的环境变量注入密钥，不写进文件。能力初始为 unknown。

```text
rsagent --root <运行目录> probe-provider configured.provider.json --output provider_probe.json
```

probe 只发送一个小工具调用请求并记录实际模型/用量，成功后按证据更新对应配置的工具能力。视觉需另用 `Provider.probe_vision()` 提供探针图与预期内容，并由人审；未测保持 unknown。模型返回的调用是建议，**不会直接执行**；参数校验失败整批拒绝。`Provider.complete()` 是库接口，尚未连接自动自然语言规划循环。当前支持配置指定的 Chat Completions 端点；不包含 Responses、流式、专用推理历史适配，extra_body 可配置官方支持的非保留参数。

有费用上限时必须给出价格、币种、来源URL与持久化 Store，并用 `budget_scope=run_id` 跨模型累计账本；未知费用/进程中断会阻止后续有限额调用。文本用保守上界预留；图像费用上界未实现，有限额图像请求会阻断。默认不重试远程请求，避免未知收费与重复提交。

## 知识和经验

检索先按软件/版本、许可、产品、格式过滤，再做精确匹配与 FTS5。候选仅显式研究查询可见，返回来源、限制、冲突、状态。版本范围使用 PEP440（如 `>=5.6,<5.7`）；MATLAB发行版使用 `exact:R2024a`。已集成 39 条候选来源、21 张候选知识卡及 10 条候选经验；发布区为空。8 项 Skill 目录的路由结果只是候选建议，不能授权执行。未实现的适配入口仍保留待验证状态。

```text
rsagent knowledge-import snapshot.json --index knowledge.sqlite --reviewed-evidence-root <已复核真实run目录>
rsagent knowledge-search MaximumLikelihood --index knowledge.sqlite --software ENVI --version 5.6 --license ENVI --format ENVI
rsagent audit-bundle <run目录>
```

快照包含摘要哈希，可离线重建索引。发布知识要求来源核查、本机run引用和已复核证据目录；`audit-bundle` 只查文件完整性，不替代真实软件/科学有效性审查。调用者提供的本机证据身份仍需交叉评审。经验注册表维护候选→复现→修复验证→回归/独立复核→发布/撤回，撤回后新候选可重启；不会自动改写已确认工作流。

## 交付与限制

原云端批次任务/验收逐项见 [COVERAGE.md](docs/COVERAGE.md)，成员接入见 [HANDOFF.md](docs/HANDOFF.md)，协议见 contracts/ 与 examples/。`releases/release_manifest.json` 是原云端包的历史清单，不是后续 Git 提交的实时清单；校验方式见 [IMPORT.md](docs/IMPORT.md)。GitHub 保存源码版本，Notion 是任务与交接入口，真实实验状态属于用户本地 SQLite。

本地 worker、三软件最小案例及 DeepSeek 两项探针已有真实证据。尚未验证：GPT 真实 API、完整自然语言自动规划、MATLAB/ArcGIS 真实窗口截图、完整实验报告与独立保留案例。训练样本最低 JM=1.1588，未通过指导书要求；诊断 OA=0.725 不代表新独立精度。CLI 不搜索或下载实验影像，也没有产品 GUI。候选方法中的重投影只校验请求，Cubic 明确拒绝；候选 DOCX 构建器仅生成技术预览，正式模板报告仍由完整证据工作流验收。
