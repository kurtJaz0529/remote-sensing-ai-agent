# 本地前置批次：T01 / T02

本批依据 Notion v1.1 与上一任务 GitHub 导入记录接续；源码分支 `codex/local-foundation-20261019`。只在新项目修改，未动 flood-eyes 的已有工作。

## 实际交付

- T01：可重跑只读环境探测脚本，Windows/CPU/内存/磁盘观测，三软件版本和许可探测。ENVI 引擎真实启动并枚举 240 项任务；MATLAB MCP 实测 R2022a，仅发现基础 MATLAB；ArcGIS Pro 专用 Python 实测 3.6、ArcInfo，Spatial/ImageAnalyst 返回 Available。
- T02：从 Notion 实验记录找回原件路径，盘点 591 个文件并生成符合 schema 的本地 manifest；原始 IMG 与检验 ROI 哈希均与 Notion 一致。选定 `图像分类/` 原件组：IMG/HDR/ROI、任务说明、操作说明和报告模板；既有成果目录只作历史对照。
- 新输入清单工具分块 SHA256、稳定排序、检测盘点期间大小/修改时间变化；拒绝链接/重解析点和输入目录内的输出，不覆盖既有清单。执行前仍须重新校验输入；清单工具不提供操作系统级防并发篡改隔离。
- 55 项测试执行，无失败/错误，1 项因 Windows 不允许创建符号链接而跳过。

## 复跑

在仓库根执行：

```powershell
./scripts/probe_environment.ps1 -OutputPath local-data/environment.json
./.venv/Scripts/python.exe scripts/inventory_inputs.py --root '<用户数据目录>' --dataset-id '<案例ID>' --output local-data/input_manifest.json
./.venv/Scripts/python.exe -m unittest discover -s tests -q
```

清单输出必须位于输入目录外，且目标文件尚不存在。完整原件清单在忽略的 `local-data/`，不上传用户原件、教材、具名报告或完整私有路径清单。公开证据在 `evidence/local-foundation/`。

## 验收边界与接续

本批是可复核前置成果，不自签任务完成。T01 尚缺真实处理/保存重读、桌面身份和 PDF 导出工具验证；三软件统一 worker 尚未实现。T02 尚缺独立样本/要求审计与新保留案例。

该影像无地图参考，保留像素坐标和像元平方，不生成虚构 CRS/公顷；比例因子未知，不能当作物理反射率。旧检验样本已经被用于诊断，不能冒充 T30 独立保留验收。

下一步由本地 Codex 按 T08 实现持久进程、可信确认复验、幂等提交、取消终态、软件/工程锁与输入登记解析，先做故障注入，再在 T09/T10/T11 分别接入真实后端。T16 真实窗口截图另行留证。知识、方法和验收矩阵保持另一成员所有权；T24 等待相应依赖，不绕过确认直接运行正式实验。

WorkBuddy 本批一次调用因 Authentication required 失败，无部分文件；没有重试或跨服务切换。脚本由本地 Codex 完成并测试。独立复核仍待其他成员执行。
