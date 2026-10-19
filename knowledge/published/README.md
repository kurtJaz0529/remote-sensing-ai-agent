# Published Knowledge Directory (`knowledge/published/`)

本目录仅存放已满足以下全部门禁条件的正式发布知识与经验卡：
1. `source_review_status == "verified"` 且全部关联 `source_ids` 均已通过复核；
2. `local_verification_status == "verified"` 且关联至少 1 个真实本地运行包 ID（`verification_run_ids` 在 `reviewed_evidence` 中 `mode == "real"` 且 `passed == True`）；
3. 由非作者成员（`cloud_codex` 或 `local_codex`）填写 `reviewer_role` 并通过 `KnowledgeIndex.promote()` 晋升。

在真实本地软件运行证据包与跨成员复核完成前，所有 `gemini_antigravity` 编写的资料卡均保留在 `knowledge/candidates/`，严禁自签晋升。
