"""Unit tests for gemini_antigravity deliverables: knowledge, skills, methods, verification, and reports."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from contracts import fingerprint, validate
from methods import (
    clump_classes,
    compute_mndwi,
    compute_ndvi,
    compute_ndwi,
    compute_pca,
    compute_tasseled_cap_tm,
    crop_raster,
    evaluate_postprocess_branches,
    isodata_classify,
    kmeans_classify,
    majority_filter,
    maximum_likelihood_classify,
    parallelepiped_classify,
    resample_raster,
    sieve_classes,
    stack_bands,
    validate_reprojection_request,
)
from reports import (
    audit_report_payload,
    audit_report_table,
    build_experiment_docx,
)
from retrieval.index import KnowledgeIndex
from scripts.evaluate_retrieval import evaluate as evaluate_retrieval_questions
from skills import FOUNDATIONAL_SKILL_IDS, SkillRegistry, load_skills_catalog
from verification import (
    CANONICAL_CLASS_SCHEMAS,
    audit_class_mapping,
    audit_envi_dataset,
    audit_sample_split,
    audit_vector_raster_consistency,
    detect_pa_ua_swap,
    evaluate_classification,
    run_all_fault_scenarios,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestAntigravityDeliverables(unittest.TestCase):
    def test_t05_t06_t28_knowledge_and_experience_contracts(self) -> None:
        sources = json.loads(
            (REPO_ROOT / "knowledge/sources/sources_catalog.json").read_text(encoding="utf-8")
        )
        cards = json.loads(
            (REPO_ROOT / "knowledge/candidates/knowledge_cards.json").read_text(encoding="utf-8")
        )
        exps = json.loads(
            (REPO_ROOT / "knowledge/candidates/experience_candidates.json").read_text(encoding="utf-8")
        )
        snapshot = json.loads(
            (REPO_ROOT / "knowledge/candidates/candidate_snapshot.json").read_text(encoding="utf-8")
        )

        self.assertGreaterEqual(len(sources), 36)
        self.assertGreaterEqual(len(cards), 18)
        self.assertEqual(len(exps), 10)

        for s in sources:
            validate("source", s)
        for c in cards:
            validate("knowledge", c)
            self.assertEqual(c["lifecycle"], "candidate")
            self.assertEqual(c["local_verification_status"], "not_run")
            self.assertEqual(c["verification_run_ids"], [])
        for e in exps:
            validate("experience", e)
            self.assertEqual(e["status"], "candidate")
            self.assertIsNone(e["reviewer_role"])

        self.assertEqual(snapshot["sha256"], fingerprint(snapshot["snapshot"]))

    def test_t29_retrieval_evaluation_isolated_and_passing(self) -> None:
        sources = json.loads(
            (REPO_ROOT / "knowledge/sources/sources_catalog.json").read_text(encoding="utf-8")
        )
        cards = json.loads(
            (REPO_ROOT / "knowledge/candidates/knowledge_cards.json").read_text(encoding="utf-8")
        )
        questions = json.loads(
            (REPO_ROOT / "verification/retrieval_eval_questions.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = KnowledgeIndex(Path(tmpdir) / "idx.sqlite")
            try:
                idx.ingest(cards, sources)
                res = evaluate_retrieval_questions(idx, questions)
            finally:
                idx.close()
        self.assertEqual(res["total"], 12)
        self.assertEqual(res["passed"], 12)

    def test_t12_skills_catalog_and_routing(self) -> None:
        skills = load_skills_catalog()
        self.assertEqual([s["skill_id"] for s in skills], list(FOUNDATIONAL_SKILL_IDS))
        reg = SkillRegistry()
        local_caps = {
            "ENVI": {"available": True, "version": "5.6.0", "licenses": ["ENVI"]},
            "MATLAB": {"available": True, "version": "R2022a", "licenses": ["MATLAB"]},
            "ArcGISPro": {
                "available": True,
                "version": "3.6.0",
                "licenses": ["ArcGISPro", "SpatialAnalyst", "ImageAnalyst"],
            },
            "PythonReference": {"available": True, "version": "3.13.7", "licenses": []},
        }
        route_envi = reg.route_backend("postprocess-and-evaluate", "ENVI", local_caps)
        self.assertEqual(route_envi["selected_software"], "ENVI")
        self.assertFalse(route_envi["used_fallback"])

        # When ArcGISPro lacks SpatialAnalyst, unsupervised-classification falls back
        limited_caps = {
            "ArcGISPro": {"available": True, "version": "3.6.0", "licenses": ["ArcGISPro"]},
            "PythonReference": {"available": True, "version": "3.13.7", "licenses": []},
        }
        route_fb = reg.route_backend("unsupervised-classification", "ArcGISPro", limited_caps)
        self.assertTrue(route_fb["used_fallback"])
        self.assertEqual(route_fb["selected_software"], "PythonReference")

    def test_t17_dataset_audit_and_class_mapping(self) -> None:
        hdr_text = """ENVI
samples = 4
lines = 3
bands = 2
header offset = 0
data type = 1
interleave = bsq
byte order = 0
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "toy.img"
            img_path.write_bytes(bytes(4 * 3 * 2))
            ok_audit = audit_envi_dataset(hdr_text, img_path=img_path, claimed_area_unit="pixel^2")
            self.assertTrue(ok_audit["passed"])

            bad_audit = audit_envi_dataset(
                hdr_text,
                img_path=img_path,
                claimed_area_unit="公顷",
                claimed_calibrated_reflectance=True,
            )
            self.assertFalse(bad_audit["passed"])

        map_audit = audit_class_mapping(
            CANONICAL_CLASS_SCHEMAS["matlab_archive"],
            CANONICAL_CLASS_SCHEMAS["envi_ex8"],
            allow_raw_code_comparison=True,
        )
        self.assertFalse(map_audit["passed"])
        self.assertEqual(map_audit["bridge_a_to_b"][3], 4)  # MATLAB 3 (built_up) -> ENVI 4
        self.assertEqual(map_audit["bridge_a_to_b"][4], 5)  # MATLAB 4 (water) -> ENVI 5
        self.assertEqual(map_audit["bridge_a_to_b"][5], 3)  # MATLAB 5 (bare_land) -> ENVI 3

        split_ok = audit_sample_split(
            [{"x": 5, "y": 5, "semantic_id": "cropland"}],
            [{"x": 20, "y": 20, "semantic_id": "cropland"}],
            min_buffer_pixels=5,
            claimed_evaluation_kind="buffered_independent_holdout",
        )
        self.assertTrue(split_ok["passed"])

    def test_t18_preprocess_methods(self) -> None:
        cube = [[[x + y * 4 for x in range(4)] for y in range(4)] for _ in range(2)]
        cropped = crop_raster(cube, 1, 3, 1, 3)
        self.assertEqual((cropped["bands"], cropped["height"], cropped["width"]), (2, 2, 2))

        res_near = resample_raster(cube, 2, 2, interpolation="nearest", is_categorical=True)
        self.assertEqual((res_near["height"], res_near["width"]), (2, 2))
        with self.assertRaises(ValueError):
            resample_raster(cube, 2, 2, interpolation="bilinear", is_categorical=True)

        stacked = stack_bands([cube[0], cube[1]], band_names=["B1", "B2"])
        self.assertEqual(stacked["bands"], 2)
        with self.assertRaises(ValueError):
            validate_reprojection_request(False, None, "EPSG:32613")

    def test_t19_spectral_methods(self) -> None:
        b_nir = [[10, 0], [60, 30]]
        b_red = [[30, 0], [20, 10]]
        ndvi = compute_ndvi(b_nir, b_red)
        self.assertAlmostEqual(ndvi["index_map"][0][0], -0.5)
        self.assertEqual(ndvi["index_map"][0][1], -9999.0)
        self.assertEqual(ndvi["zero_denominator_count"], 1)

        ndwi = compute_ndwi(b_red, b_nir)
        mndwi = compute_mndwi(b_red, b_nir)
        self.assertEqual(ndwi["index_name"], "NDWI")
        self.assertEqual(mndwi["index_name"], "MNDWI")

        cube6 = [
            [[10 + b * 3 + x * 2 + y for x in range(5)] for y in range(5)]
            for b in range(6)
        ]
        pca_res = compute_pca(
            cube6,
            fit_domain="train_split_only",
            train_pixel_coords=[(0, 0), (1, 2), (3, 4), (4, 1)],
            for_supervised_evaluation=True,
            n_components=3,
        )
        self.assertEqual(len(pca_res["components_cube"]), 3)
        self.assertEqual(pca_res["fitted_sample_count"], 4)

        kt_res = compute_tasseled_cap_tm(cube6)
        self.assertIn("Third (Wetness-related)", kt_res["component_names"])

    def test_t20_classification_methods(self) -> None:
        cube = [
            [[(10 + (y % 2) * 2) if x < 3 else (80 + (y % 2) * 2) for x in range(6)] for y in range(4)],
            [[(15 + (y % 2) * 2) if x < 3 else (85 + (y % 2) * 2) for x in range(6)] for y in range(4)],
        ]
        samples = {
            1: [[10, 15], [12, 17], [9, 16], [11, 14]],
            2: [[80, 85], [82, 87], [81, 84], [79, 86]],
        }
        pp = parallelepiped_classify(cube, samples, std_multiplier=3.0, overlap_policy="min_standardized_distance")
        self.assertEqual(pp["class_map"][0][0], 1)
        self.assertEqual(pp["class_map"][0][5], 2)

        mlc = maximum_likelihood_classify(cube, samples)
        self.assertEqual(mlc["class_map"][0][0], 1)
        self.assertEqual(mlc["class_map"][0][5], 2)

        km = kmeans_classify(cube, k=2, seed=42)
        self.assertEqual(km["cluster_count"], 2)

        # ISODATA with active split triggered by low split_std_threshold
        iso_active = isodata_classify(
            cube,
            k_init=2,
            k_min=2,
            k_max=4,
            max_iter=4,
            min_samples_per_cluster=2,
            split_std_threshold=0.1,
            merge_distance_threshold=0.01,
        )
        self.assertFalse(iso_active["degenerated_to_kmeans"])
        self.assertGreater(iso_active["split_events"], 0)

    def test_t21_t22_postprocess_and_evaluation(self) -> None:
        raw_map = [
            [1, 1, 2, 1, 1],
            [1, 1, 1, 1, 1],
            [5, 5, 5, 5, 5],
            [4, 4, 4, 4, 4],
            [4, 4, 4, 4, 4],
        ]
        sieved = sieve_classes(raw_map, min_blob_size=2, connectivity=8)
        # Isolated single pixel of class 2 at (0, 2) becomes 0 (Unclassified)
        self.assertEqual(sieved[0][2], 0)
        clumped = clump_classes(raw_map, kernel_size=3)
        maj = majority_filter(raw_map, window_size=3)
        branches = evaluate_postprocess_branches(
            raw_map,
            {"sieve_2px": sieved, "clump_3x3": clumped, "majority_3x3": maj},
            CANONICAL_CLASS_SCHEMAS["envi_ex8"],
        )
        self.assertIn("sieve_2px", branches["branches"])

        vec_audit = audit_vector_raster_consistency(
            {1: 9, 2: 1, 4: 10, 5: 5},
            [
                {"GRIDCODE": 1, "PIXEL_CNT": 9},
                {"GRIDCODE": 2, "PIXEL_CNT": 1},
                {"GRIDCODE": 4, "PIXEL_CNT": 10},
                {"GRIDCODE": 5, "PIXEL_CNT": 5},
            ],
        )
        self.assertTrue(vec_audit["passed"])

    def test_t23_t26_report_builder_and_10_fault_scenarios(self) -> None:
        fault_res = run_all_fault_scenarios()
        self.assertTrue(fault_res["all_passed"])
        self.assertEqual(fault_res["passed_scenarios"], 10)

        manifest = {
            "run_id": "RUN-UNITTEST-001",
            "execution_mode": "headless_api",
            "evaluation_kind": "reference_agreement",
            "has_crs": False,
            "has_verified_scale_factor": False,
            "review_status": "pending_review",
            "table_metrics": {
                "post_tbl": {
                    "water": {"raw_ml": 134, "ml_sieve": 124},
                }
            },
            "artifacts": [],
        }
        payload = {
            "title": "Canon City 遥感分类测试报告",
            "sections": {
                "task_and_env": "通过 envipyengine 无头任务接口执行。",
                "dataset_audit": "无 CRS，面积以 pixel^2 统计；存储数值范围为 0..100。",
                "spectral_transform": "K-T 变换第三分量记为 Third (Wetness-related)。",
                "accuracy_evaluation": "基于目视参考 ROI 一致性（reference_agreement）进行对比。",
            },
            "tables": [
                {
                    "table_id": "post_tbl",
                    "title": "后处理对比表",
                    "columns": [
                        {"column_id": "raw_ml", "bound_id": "raw_ml", "header": "ML 原图"},
                        {"column_id": "ml_sieve", "bound_id": "ml_sieve", "header": "ML_Sieve"},
                    ],
                    "rows": [
                        {
                            "row_id": "water",
                            "bound_row_id": "water",
                            "label": "水域 (pixel^2)",
                            "cells": {"raw_ml": 134, "ml_sieve": 124},
                        }
                    ],
                }
            ],
            "figures": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_docx = Path(tmpdir) / "report.docx"
            res = build_experiment_docx(payload, manifest, out_docx)
            self.assertTrue(res["passed"])
            self.assertTrue(out_docx.exists())
            self.assertGreater(res["size_bytes"], 1000)


if __name__ == "__main__":
    unittest.main()
