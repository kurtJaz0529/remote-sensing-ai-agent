# 遥感 AI Agent 知识库与经验晋升体系（`knowledge/`）

本目录由 **`gemini_antigravity`** 负责建设与维护，严格遵循 `contracts/source.schema.json`、`contracts/knowledge.schema.json` 与 `retrieval/index.py` 的三级生命周期契约（`raw` -> `candidate` -> `published` / `deprecated`）。

## 目录结构与职责映射

| 子目录 / 文件 | 对应任务 | 内容说明 | 状态 / 生命周期 |
| :--- | :--- | :--- | :--- |
| `sources/sources_catalog.json` | `T05` | 覆盖 9 大领域的 36 条结构化资料源目录（含主备检索路线、权威级别、许可与字段完整度） | 候选待复核 |
| `sources/research_questions.json` | `T05` | 9 大领域检索问题清单、必答研究问题与停止检索判据（Stopping Rules） | 候选待复核 |
| `candidates/knowledge_cards.json` | `T06` | 18 张软件方法卡、遥感算法卡、跨软件冲突卡、历史高发错误卡与标准工作流卡 | `lifecycle: "candidate"`, `local_verification_status: "not_run"` |
| `candidates/conflicts_and_errors.md` | `T06` | 跨软件语义冲突表（类别编码、平行六面体、Sieve/Clump、K-T 第三分量）与 10 类历史错误拦截规则 | 候选待复核 |
| `candidates/experience_candidates.json` | `T28` | 从 MATLAB 与 ENVI 历史实验归档提炼的 10 条候选经验规则、触发器与双人晋升门禁 | `lifecycle: "candidate"` |
| `candidates/candidate_snapshot.json` | `T06` / `T08` | 通过 `KnowledgeIndex.ingest()` 校验并导出的候选知识索引快照 | 自动生成快照 |
| `published/` | `T06` / `T28` | **仅存放已完成真实本地软件运行验证（`verified`）且通过双人独立复核的知识/经验卡** | 当前保持为空（严禁自签晋升） |

## 严格门禁规则（Governance Rules）

1. **禁止自签晋升**：`gemini_antigravity` 编写的资料卡与经验规则一律写入 `knowledge/candidates/`，保持 `local_verification_status: "not_run"` 与 `verification_run_ids: []`。
2. **晋升前置条件**：必须由 `local_codex` 在真实本地软件运行后产出包含 `manifest.json`、`structured_log.jsonl`、`artifacts_index.json` 的运行包（`runs/<run_id>`），再由 `cloud_codex` 或跨成员复核后调用 `KnowledgeIndex.promote()` 晋升至 `published`。
3. **版本范围语法**：所有卡片的 `software_version_scope` 必须为 `exact:<version>`（如 `exact:R2022a`）或合法的 PEP 440 范围表达式（如 `>=5.6,<5.7`、`>=3.6,<3.7`、`>=0.1`），确保 `retrieval/index.py` 版本过滤零异常。
