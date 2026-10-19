# 本地 MCP 集成交付 · 0.1.0.dev3

本批继续 Notion 的 T01–T32 计划，保留原任务编号。全部软件入口使用 MCP；未调用 Computer Use，也未启动 AGY/Gemini 委派。已审查并集成现有分支 `c3fa78e55d9adfb3ec2b0da95c5a481a4590ee75` 的候选组件。此处记录实现与运行结果，正式实验及独立验收仍有缺项。

## 已执行的真实验证

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| ENVI 原生最大似然及 3×3 ClassificationSmoothing | MCP → 持久 worker → ENVI 5.6；Completed，原件哈希不变；256,000 像元与独立高斯判别结果零差异 | `RUN-e092b96f272e4415bb5eea661ce1285e` |
| 训练样本及历史检验点 | 1,346 个训练像元、200 个诊断点，最近 Chebyshev 距离 6；最低 JM=1.15878668（建设用地/裸地），未通过指导书 JM>1.9 要求 | classification/sample-audit.json |
| 分类指标 | 最大似然 OA=0.725、Kappa=0.6629592181；平滑后 OA=0.725、Kappa=0.6620791349；均为历史点诊断，未证明独立精度或平滑改善 | classification/diagnostic-metrics.json |
| ENVI Classic | 专用 MCP 启动并冻结三步 diagnostic 计划；取得主窗口、打开文件参数、六波段列表的三张未编辑原图；会话正常关闭 | classic/evidence-summary.json |
| 第二个用户目录 | 对用户指定目录登记 196 个文件，71 张 PNG 结构检查通过；该检查不证明像素/地理/语义正确 | second-case/input-audit-summary.json |
| 第二幅 RGB 原图 | 用户三峡库区影像 1792×1536；原生 SubsetRaster 的 64×64×3 裁剪与源 PNG 解码结果零差异；原件未变 | `RUN-f1d775c028654d5f97914605d13edc06` |
| DeepSeek 工具/视觉 | 经受限 MCP 进行了两个真实请求；返回合法工具提议及合成纯红图识别结果。没有执行提议、没有发送用户影像 | provider/；费用按峰值/未命中价格保守估算 USD 0.0002046，非账单金额 |
| 归档恢复 | 分类包 17 文件与第二影像包 9 文件，均恢复到新目录，manifest/文件哈希一致 | component-review/verification.json 的 recovery |

上述公开证据均在 [evidence/diagnostic-integration-20261019](../evidence/diagnostic-integration-20261019/)。原始影像、样本坐标/标签 CSV、完整输入 manifest、原生输出、SQLite 与归档 ZIP 留在本地 `local-data/`。

Classic 的三步 diagnostic 完整性仅证明该探针完成。它没有登记完整实验输入或覆盖分类指导书全流程；原服务返回的“可以进入报告生成”不能据此解释为完整实验报告门通过。MATLAB/ArcGIS 的必需真实窗口截图尚未取得。

## 集成审查及修复

- 拒绝尚未实现的 Cubic 插值；修复双线性上采样左/上边界，避免错误混入下一行/列。
- PNG/BIP 验证保留失败 run：`RUN-078e79aa8edb436b9e5f01d2445b4331`。故障在读取器假定 BSQ；修复后按实际 HDR 解码 BSQ/BIL/BIP，新 revision 通过。已查询原 job 为 failed 后关闭该批次持久服务，未重提原 job。
- 样本距离检查与独立性证明分开。空集、重复/非法坐标被拒绝；无冻结评价协议及未用于调参的证据，返回 unknown。细分标签显式映射到 task schema 的 evaluation_kind。
- HDR 中存在 map info/缩放字段不足以证明米制网格或反射率校准。物理面积、校准声明需要额外验证。
- 拒绝小数/未知分类代码、非有限输入和负/重复 PCA 拟合坐标。
- 报告检查拒绝缺失/未知表格绑定、NaN、图片路径越界、哈希不符和缺少必需证据；DOCX 构建器限显式技术预览，正式模板保持生成尚未验证。
- Skill 路由不虚构 Python 可用性；所有候选路由返回 execution_eligible=false。目录中的占位适配器仍不可执行。
- 原“正式”检索题已进入公开开发分支，因此仅作为公开回归题移入 `tests/fixtures/public_retrieval_regression.json`。12/12 是公开回归结果，不能作为保留验收结论。

组件通过 MCP 只读接入已冻结原生运行包：两套混淆矩阵复算一致；16×16 子区的存储值归一化差值与 PCA 特征值对照通过。这是 Python 重实现的组件检查，不宣称新的原生光谱流程或校准地表指数。39 条来源、21 张知识卡和 10 条经验均为候选，默认发布检索为空。

## 验证和安装

Windows / Python 3.13.7：108 项单元、协议和回归测试零失败，一项 Windows 符号链接权限测试跳过。新的虚拟环境安装 dev3 wheel，以 Python 隔离模式确认模块来自已安装包、JSON 资源可读、四个 MCP 工具可发现，并通过算术与报告门冒烟检查。两种验证范围分别记录，未将安装测试当作真实软件验收。

```powershell
python -m pip install "releases/rsagent_cloud_core-0.1.0.dev3-py3-none-any.whl[mcp,science,documents]"
python -m orchestrator.mcp_server --root <独立runtime目录> --http --port 8765
```

在源码目录复现组件测试：`python -m unittest discover -s tests -v`。实际软件环境仍分别使用 ENVI 专用 Python、ArcGIS Pro Python 与 MATLAB R2022a；ENVI RGB 适配器额外需要该环境中的 Pillow。固定案例脚本中的源路径与哈希只适用于已登记原件，其他数据须重新实现/审查能力并确认计划。

开发工具 `scripts.probe_provider_mcp` 只允许两个固定探针，以进程内环境变量传递所需凭据。每类请求先持久化 claim，再发送；started/failed/unknown 都不会自动重试。GPT 的真实 API 因无配置凭据仍未验证。

## 任务推进边界

| 任务 | 当前已落实 | 仍待验收 |
| --- | --- | --- |
| T01–T03 | 环境/输入登记、协议、核心与跨成员候选分支集成 | 独立签验及部分桌面能力 |
| T04 | DeepSeek 真实工具与视觉探针；错误/用量/幂等保护 | GPT API、自动规划循环、图像预算上界 |
| T05–T07 | 来源、知识候选、需求矩阵/截图规范集成 | 逐来源核实、指导书全流程冻结与复核 |
| T08–T11、T15 | 三软件统一 MCP 最小真实运行、锁/确认/状态/恢复；ENVI 分类诊断 | 更广方法和真实中断的独立审查 |
| T12–T14 | 候选 Skill、离线索引、输入确认与篡改阻断 | 占位入口和客户端实际加载；自然语言/OCR/语义规划 |
| T16 | ENVI Classic 三张原始诊断截图 | MATLAB/ArcGIS 截图及完整实验各阶段 |
| T17–T19 | 数据/样本审计联调、原生裁剪和 Python 光谱算术检查 | 实际重投影/重采样/镶嵌等；校准条件；更多原生方法 |
| T20–T22 | 原生 ML/majority、独立判别复算、真实输出诊断矩阵；其他算法候选 | 合格 ROI、未执行的 K-Means/ISODATA/Sieve/Clump 原生分支及矢量闭环 |
| T23–T25 | 报告门/预览组件及真实分类诊断 | 指导书完整截图、模板报告/PDF、正式端到端及独立科学验收 |
| T26–T28 | 故障回归、两包恢复、候选经验隔离 | 完整实验故障覆盖、科学复核及经验发布 |
| T29–T30 | 公开检索回归、第二幅用户影像技术验证 | 新的非公开题集、未参与调参的用户案例与知识效果比较 |
| T31–T32 | dev3 wheel 和干净安装冒烟证据 | 产品首版签验、用户实际试用与成本/干预基线 |

下一步先补齐合格且经独立解释的 ROI，冻结未用于调参的保留评价协议；完善三软件所需截图及正式报告工作流，再向另一成员提交 T25/T30 科学验收。当前训练标签和历史检验点不得通过重新拆分而改称新独立数据。
