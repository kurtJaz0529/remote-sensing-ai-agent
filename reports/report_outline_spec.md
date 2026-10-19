# 遥感实验报告标准大纲与证据链审计规范（T07 / T23）

> **维护责任**：`gemini_antigravity`  
> **执行实现**：`reports/report_builder.py`  
> **关联验收项**：`R10`、`R11`、`CHK-REPORT-TABLE-COL-001`、`CHK-REPORT-HONESTY-001`、`CHK-EVAL-KIND-001`、`CHK-SPEC-KT-THIRD-001`

---

## 一、实验报告强制章节结构（7 章标准大纲）

1. **第一章：任务契约与本地软件环境探针（Task Contract & Environment Probe）**
   - 必须绑定 `task_id`、`run_id`、软件名称与精确版本（ENVI 5.6 + IDL 8.8、MATLAB R2022a 9.12、ArcGIS Pro 3.6）。
   - 必须如实披露许可证与工具箱边界（例如 MATLAB 仅含基础许可证 Base License，无 Image Processing / Statistics / Mapping Toolboxes）。
   - 必须声明执行模式 `execution_mode`（`headless_api`、`batch` 或 `interactive_gui`）。

2. **第二章：数据集元数据、空间参考、定标与样本空间缓冲审计（Dataset & Sample Audit）**
   - 列出栅格维度（`640 x 400 x 6`）、存储格式（`uint8 BSQ`）、文件 SHA256 指纹。
   - **空间参考边界（`CHK-AUDIT-CRS-001`）**：当 `.hdr` 无 `map info` / CRS 时，面积单位仅允许使用 `pixel` 与 `pixel^2`，严禁出现 `公顷 (hm²/ha)`、`平方千米 (km²)` 等无依据物理面积单位。
   - **辐射定标边界（`CHK-AUDIT-SCALE-001`）**：当未提供经验证的反射率缩放因子时，仅报告存储数值范围（`0..100`），严禁声称已转换为 `0..1` 真实地表反射率。
   - **类别编码字典与样本空间审计（`CHK-CLASS-MAP-001`、`CHK-AUDIT-BUFFER-001`）**：显式列出 `native_code <-> semantic_id` 映射表、训练/验证点重叠数、最小 Chebyshev 距离与 `evaluation_kind`。

3. **第三章：光谱指数、主成分分析（PCA）与缨帽变换（K-T Transform）**
   - 说明 `float64` 转换与零分母掩膜（`nodata = -9999.0`）统计。
   - 披露 PCA 拟合域 `fit_domain`（`full_image_unsupervised` 或 `train_split_only`）及各主成分方差贡献率。
   - **K-T 第三分量命名规范（`CHK-SPEC-KT-THIRD-001`）**：针对 Landsat 5 TM，第三分量必须标注为 `Third (Wetness-related)`，不得直接等同于已标定的绝对土壤湿度物理量。

4. **第四章：非监督与监督分类实现与参数边界（Classification Methods）**
   - 非监督分类（K-Means / ISODATA）：披露迭代次数、中心初值种子；ISODATA 必须披露 `split_events` 与 `merge_events` 计数，若均为 `0` 必须注明退化为同初值 K-Means（`degenerated_to_kmeans = True`）。
   - 监督分类（最大似然 / 平行六面体）：披露类内协方差条件数与正则化策略；平行六面体必须披露 `overlap_policy`、`overlap_ratio` 与 `unclassified_ratio`。

5. **第五章：分类后处理多分支对比与细长水体保持分析（Post-processing Comparison）**
   - 对比原始分类与 Majority、Clump、Sieve、Clump+Sieve 分支的像元面积与精度变化。
   - 严格区分 ENVI 原生算子（`native_envi_postprocess`）与纯矩阵近似算子（`approximate_postprocess`）。
   - **表格列序语义校验（`CHK-REPORT-TABLE-COL-001`）**：表格每列必须显式绑定 `branch_id` 与 `semantic_id`，严禁发生表头与数值列错位（如历史实验八表6中 `ML_Clump` 与 `ML_Sieve` 或建设用地与水域列互换）。
   - **细长水体损失告警（`CHK-POST-WATER-LOSS-001`）**：当 Majority 或 Clump 导致水体像元或制图精度显著下降时，必须在正文单列风险说明。

6. **第六章：分类精度验证与误差矩阵分析（Accuracy Evaluation）**
   - 输出统一 `semantic_id` 空间的 $C \times (C+1)$ 非对称混淆矩阵（行=参考真实类别，列=预测类别含 `0=Unclassified`）。
   - 报告总体精度（OA）、Kappa 系数、各类别制图精度（PA）与用户精度（UA），并通过 `detect_pa_ua_swap` 校验。
   - **评估性质诚实披露（`CHK-EVAL-KIND-001`）**：当 `evaluation_kind` 为 `resubstitution`、`spatially_contaminated_holdout`、`diagnostic_holdout` 或 `reference_agreement` 时，严禁使用“独立样本泛化精度”或“全图无偏面积精度”措辞。

7. **第七章：冻结运行包证据索引与复核签名（Evidence Manifest & Sign-off）**
   - 列出全部输入、输出、图表产物路径与 SHA256 摘要。
   - 记录作者角色（`author_role`）、复核人角色（`reviewer_role`）与双签状态（未完成独立复核前固定为 `待复核`）。
