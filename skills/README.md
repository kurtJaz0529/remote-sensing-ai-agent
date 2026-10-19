# 遥感 AI Agent 8 项基础 Skills 体系与能力路由（`skills/`｜T12）

本目录由 **`gemini_antigravity`** 负责建设，定义了客户端无关（Client-Neutral）的 8 项遥感基础技能契约（`skills/skill_schema.json`）、结构化技能目录（`skills/catalog/skills_catalog.json`）与软件能力路由器（`skills/loader.py`）。

## 8 项基础 Skills 阶段流水线

| 阶段序号 | Skill ID | 中文名称 | 入口模块 | 核心验收检查 ID |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `task-intake` | 任务理解与契约生成 | `skills.loader:route_skill_backend` | `CHK-INTAKE-SCHEMA-001`, `CHK-INTAKE-EVAL-KIND-001` |
| 2 | `dataset-audit` | 数据集元数据、定标边界与样本空间缓冲审计 | `verification.dataset_audit:audit_envi_dataset` | `CHK-AUDIT-HDR-001`, `CHK-AUDIT-CRS-001`, `CHK-AUDIT-SCALE-001`, `CHK-CLASS-MAP-001`, `CHK-AUDIT-BUFFER-001` |
| 3 | `raster-preprocess` | 栅格预处理（裁剪、重投影、重采样、波段堆栈） | `methods.preprocess:resample_raster` | `CHK-PREPROC-CROP-001`, `CHK-PREPROC-RESAMPLE-CAT-001`, `CHK-PREPROC-STACK-001` |
| 4 | `spectral-transform` | 光谱指数、PCA 主成分变换与 K-T 缨帽变换 | `methods.spectral` | `CHK-SPEC-FLOAT-001`, `CHK-SPEC-ZERO-DENOM-001`, `CHK-SPEC-PCA-LEAK-001`, `CHK-SPEC-KT-THIRD-001` |
| 5 | `unsupervised-classification` | 非监督分类（K-Means 与 ISODATA 动态聚类） | `methods.classification` | `CHK-CLASS-KMEANS-001`, `CHK-CLASS-ISO-001` |
| 6 | `supervised-classification` | 监督分类（最大似然分类与平行六面体分类） | `methods.classification` | `CHK-CLASS-MLC-001`, `CHK-CLASS-PP-001`, `CHK-CLASS-MAP-001` |
| 7 | `postprocess-and-evaluate` | 分类后处理（Majority/Sieve/Clump）与独立精度验证 | `methods.postprocess` | `CHK-POST-MODE-001`, `CHK-POST-WATER-LOSS-001`, `CHK-EVAL-MATRIX-001`, `CHK-EVAL-PA-UA-001` |
| 8 | `deliver-and-learn` | 证据绑定报告生成、双签归档与经验规则晋升 | `reports.report_builder:build_experiment_docx` | `CHK-EVIDENCE-MANIFEST-001`, `CHK-SCREENSHOT-ID-001`, `CHK-REPORT-HONESTY-001`, `CHK-REPORT-TABLE-COL-001` |

## 本机软件许可与路由规则（基于 T01 实测探针）

- **ENVI 5.6 + IDL 8.8 (`>=5.6,<5.7`)**：支持 `envipyengine` 240 个 Tasks 及 IDL 批处理桥接。
- **MATLAB R2022a (`exact:R2022a`)**：本机仅含基础 MATLAB 许可（`licenses: ["MATLAB"]`，无 `Image_Toolbox`、`Statistics_Toolbox`、`Map_Toolbox`），路由器自动拦截依赖工具箱的后端调用，切换至基础矩阵实现或回退至 `ENVI` / `ArcGISPro` / `PythonReference`。
- **ArcGIS Pro 3.6 (`>=3.6,<3.7`)**：含 `ArcGISPro`、`SpatialAnalyst`、`ImageAnalyst` 许可。
- **验证状态标签**：所有外部软件后端当前均标注为 `"verification_status": "pending_local_tool_verification"`，待 `local_codex` 端到端运行验证后更新。
