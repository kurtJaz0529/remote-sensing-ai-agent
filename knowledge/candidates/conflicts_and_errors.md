# 跨软件语义冲突、历史高发错误与版本边界索引（T06）

> **维护责任**：`gemini_antigravity`
> **关联文件**：`knowledge/candidates/knowledge_cards.json`、`knowledge/sources/sources_catalog.json`、`knowledge/candidates/experience_candidates.json`
> **状态说明**：当前所有卡片均处于 `lifecycle: "candidate"`、`local_verification_status: "not_run"`。待 `local_codex` 在真实软件运行包（`runs/<run_id>/`）上完成本地验证并由 `cloud_codex` 独立复核后，方可调用 `KnowledgeIndex.promote()` 晋升至 `knowledge/published/`。

---

## 一、跨软件语义冲突表（Cross-Software Conflict Registry）

| 冲突编号 | 对应卡片 ID | 冲突主题 | 软件/环境 A 行为 | 软件/环境 B 行为 | Agent 强制消歧与降级策略 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `CONF-01` | `CARD-CONF-001` | **类别编码字典不一致（Class Code Mapping）** | **MATLAB 历史归档**：`1=耕地, 2=有林地, 3=建设用地, 4=水域, 5=裸地, 6=其他, 0=未分类` | **ENVI 实验八归档**：`1=耕地, 2=有林地, 3=裸地, 4=建设用地, 5=水域, 6=其他, 0=未分类`（编码 3/4/5 完全不同） | 严禁按原始数字编码直接跨软件对比或构建混淆矩阵；必须先通过 `class_mapping_manifest` 映射至统一语义 ID（`cropland`, `forest`, `bare_land`, `built_up`, `water`, `other`, `unclassified`）。 |
| `CONF-02` | `CARD-CONF-002` | **平行六面体多重落入（Parallelepiped Overlap）** | **ENVI `ParallelepipedClassificationTask`**：按 ROI 类别顺序或优先规则分配，参数为各波段标准差倍数 `MAX_STDEV_FROM_MEAN` | **MATLAB 自写实现**：若采用 `for c = 1:C` 循环赋值，后遍历类别会静默覆盖先遍历类别的像元 | 必须在算法契约中显式声明 `overlap_policy`（`first_class`、`min_standardized_distance` 或 `unclassified_on_overlap`），并在运行日志中单列多重落入像元比例 `overlap_ratio`。 |
| `CONF-03` | `CARD-CONF-003` | **分类后小斑块去除（Sieve + Clump vs 近似）** | **ENVI 原生后处理**：`ClassificationClumpingTask`（形态学膨胀+腐蚀连接邻近同类别）+ `ClassificationSievingTask`（连通域小于阈值置为 `0=Unclassified`） | **无工具箱 MATLAB 近似**：多数滤波（Majority Filter）或四/八邻域连通域直接重赋邻域众数（无置零步） | 严禁将 MATLAB 近似结果标注为“ENVI 原生 Sieve/Clump 结果”；必须在报告中区分 `native_envi_postprocess` 与 `approximate_postprocess`，并统计水体等细长地物损失率。 |
| `CONF-04` | `CARD-ERR-003` | **Landsat 5 TM K-T 变换第三分量命名** | **Crist & Cicone (1984) 反射率/DN 系数下**：第三分量定义为 `Third`（早期文献曾称 `Yellowness`），仅部分反映土壤/植被水分特征 | **部分教材/报告误写**：直接将第三分量等同于纯湿度指标 `Wetness` 并做绝对含水量推断 | 统一使用 `Brightness / Greenness / Third (Wetness-related)` 术语，禁止把 `Third` 当作已标定的绝对土壤湿度物理量。 |

---

## 二、历史实验高发错误卡片索引（Historical Error Cards）

| 错误编号 | 卡片 ID | 错误类别 | 历史出处 | 触发条件与危害 | 独立验证器拦截规则（`verification/`） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ERR-01` | `CARD-ERR-001` | `uint8_underflow_zero_div` | MATLAB 实验报告 | 在 `uint8` 栅格上直接计算 `(B4 - B3) / (B4 + B3)`，当 `B4 < B3` 时无符号减法截断为 `0`，分母为 `0` 时产生 `NaN/Inf` | `methods/spectral.py` 强制 `float64` 转换；分母 `abs(denom) <= 1e-12` 像元写入 `nodata=-9999.0` 并输出 `zero_denominator_mask`。 |
| `ERR-02` | `CARD-ERR-002` | `missing_crs_and_scale` | MATLAB & ENVI 实验归档 | `can_tmr.hdr` 无 `map info`，像元值范围 `0..100`；若强行声称公顷/平方千米面积或已标定 `0..1` 地表反射率，属于无依据外推 | `verification/dataset_audit.py` 检测 `has_crs == False` 时阻塞物理面积单位声明；检测 `scale_factor` 未验证时阻塞定标物理量声明。 |
| `ERR-03` | `CARD-ERR-003` | `kt_third_component_misuse` | MATLAB 实验报告 | 将 K-T 变换第三分量直接混同为绝对湿度 `Wetness` | `reports/report_builder.py` 文本审计器检查 K-T 章节是否包含 `Third` 分量边界说明。 |
| `ERR-04` | `CARD-ERR-004` | `pca_train_test_leakage` | 监督分类/特征提取通用规范 | 在全图或含测试样本集合上拟合 PCA 均值与协方差，再在同批测试集上报告泛化精度 | `methods/spectral.py` 要求显式传入 `fit_domain`（`full_image_unsupervised` vs `train_split_only`），监督评估下若 `fit_domain != "train_split_only"` 触发泄露告警。 |
| `ERR-05` | `CARD-ERR-005` | `categorical_bilinear_resample` | 栅格预处理通用规范 | 对分类图/ROI 掩膜使用 `bilinear` 或 `cubic` 重采样，产生类别编码均值（如 `1` 与 `4` 插出 `2` 或 `3`） | `methods/preprocess.py` 与 `verification/fault_scenarios.py` 检测到 `is_categorical=True` 且 `interpolation != "nearest"` 时直接拒绝执行。 |
| `ERR-06` | `CARD-ERR-006` | `resubstitution_as_independent` | ENVI 实验八归档 | 训练/验证共用同一 ROI，或训练/验证像元距离小于 `5` 像元缓冲，却在报告中写成“独立测试集真实泛化精度” | `verification/dataset_audit.py` 强制输出 `evaluation_kind`（`resubstitution` / `spatially_contaminated_holdout` / `buffered_independent_holdout`），禁止把回代精度写为独立泛化精度。 |
| `ERR-07` | `CARD-ERR-007` | `pa_ua_swap_and_omission` | ENVI 实验八（表4 vs 表5） | 混淆矩阵行/列方向顛倒导致制图精度（PA）与用户精度（UA）互换，或漏算 `0=Unclassified` 列导致精度虚高 | `verification/classification_eval.py` 固定生成 `C x (C+1)` 矩阵（含 `Unclassified` 列），并内置 `detect_pa_ua_swap()` 自动比对报告数值。 |
| `ERR-08` | `CARD-ERR-008` | `table_column_swap_and_water_loss` | ENVI 实验八（表6） | 对比表格表头写 `ML_Clump / ML_Sieve`，但数据列填反；Majority/Clump 吞噬细长水体（水体 PA 从 `92.54%` 暴跌至 `69.40%`）却未告警 | `reports/report_builder.py` 校验表格列绑定 manifest 字段 ID；`methods/postprocess.py` 对细长/小面积类别减幅超阈值触发 `water_loss_warning`。 |
| `ERR-09` | `CARD-ERR-009` | `api_gui_wording_conflation` | 遥感 Agent 运行契约 | 后台通过 `envipyengine`、`matlab -batch` 或 `arcpy` 无头执行，报告正文却描写“点击菜单栏/弹出对话框”等伪造 GUI 操作 | `reports/report_builder.py` 审计 `execution_mode` 与报告措辞，无头模式下严禁出现伪造的点击/菜单操作描述。 |
| `ERR-10` | `CARD-ERR-010` | `isodata_no_split_merge` | MATLAB 实验报告 | 自写“ISODATA”脚本仅跑固定 K 值迭代，未触发任何分裂（Split）或合并（Merge），实质退化为 K-Means | `methods/classification.py` 精确记录 `split_events` 与 `merge_events`；若二者均为 `0`，必须标注 `degenerated_to_kmeans: True`。 |

---

## 三、本机软件版本与工具箱边界（来自 T01 实测探针）

1. **ENVI 5.6 + IDL 8.8**
   - 范围标识：`>=5.6,<5.7`
   - 实测路径：`C:\Program Files\Harris\ENVI56\IDL88\bin\bin.x86_64\taskengine.exe`
   - 能力边界：`envipyengine` 可正常枚举 240 个 ENVI Tasks；部分经典分类（如 `MaximumLikelihoodClassification`）若不在 `ENVITask` 列表内，需通过 IDL 批处理脚本桥接或本地方法包执行，并在运行证据中如实记录。
2. **MATLAB R2022a (`9.12.0.1884302`)**
   - 范围标识：`exact:R2022a`
   - 能力边界：**仅安装基础 MATLAB 许可证（Base MATLAB only）**，未安装 Image Processing Toolbox、Statistics and Machine Learning Toolbox、Mapping Toolbox。
   - 强制约束：禁止调用 `kmeans`、`imresize`、`bwlabel`、`multibandread`（若依赖工具箱特性）等受限函数；所有矩阵、滤波、距离、特征分解均须使用基础 MATLAB 线性代数原语或纯 Python/基础矩阵算子实现。
3. **ArcGIS Pro 3.6 (`3.6.0.59527`)**
   - 范围标识：`>=3.6,<3.7`
   - 实测路径：`F:\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`
   - 能力边界：`ArcInfo (Advanced)` 许可，`Spatial Analyst` 与 `Image Analyst` 扩展均为 `Available`，支持栅格转面、重投影、空间叠加与制图导出。
