"""10 mandatory fault-injection verification scenarios covering historical experiment errors (T26)."""
from __future__ import annotations

from typing import Any

from methods.classification import isodata_classify, parallelepiped_classify
from methods.postprocess import evaluate_postprocess_branches, majority_filter
from methods.preprocess import resample_raster
from methods.spectral import (
    compute_normalized_difference,
    compute_pca,
    compute_tasseled_cap_tm,
)
from reports.report_builder import audit_report_payload, audit_report_table
from verification.classification_eval import detect_pa_ua_swap, evaluate_classification
from verification.dataset_audit import (
    CANONICAL_CLASS_SCHEMAS,
    audit_class_mapping,
    audit_envi_dataset,
    audit_sample_split,
)

SAMPLE_CAN_TMR_HDR = """ENVI
description = {Canon City, CO, Landsat TM}
samples = 640
lines = 400
bands = 6
header offset = 0
file type = ENVI Standard
data type = 1
interleave = bsq
byte order = 0
band names = {TM Band 1, TM Band 2, TM Band 3, TM Band 4, TM Band 5, TM Band 7}
wavelength = {0.485, 0.560, 0.660, 0.830, 1.650, 2.215}
"""


def fault_01_uint8_underflow_and_zero_denom() -> dict[str, Any]:
    """FAULT-01: Verify float64 cast and zero-denominator mask (-9999.0) when band_a < band_b or a+b==0."""
    band_a = [[10, 0], [40, 25]]
    band_b = [[30, 0], [10, 25]]
    res = compute_normalized_difference(band_a, band_b, nodata=-9999.0)
    neg_preserved = abs(res["index_map"][0][0] - (-0.5)) < 1e-6
    zero_masked = res["index_map"][0][1] == -9999.0 and res["zero_denominator_mask"][0][1] == 1
    caught_disabled_float = False
    try:
        compute_normalized_difference(band_a, band_b, enforce_float64=False)
    except ValueError as exc:
        caught_disabled_float = "CHK-SPEC-FLOAT-001" in str(exc)

    passed = neg_preserved and zero_masked and caught_disabled_float
    return {
        "scenario_id": "FAULT-01",
        "historical_case_id": "HIST-ERR-01",
        "check_id": "CHK-SPEC-FLOAT-001",
        "passed": passed,
        "details": {
            "negative_difference_preserved": neg_preserved,
            "zero_denominator_masked": zero_masked,
            "disabled_float64_blocked": caught_disabled_float,
        },
    }


def fault_02_missing_crs_and_unverified_scale() -> dict[str, Any]:
    """FAULT-02: Inject metric area ('km^2') and calibrated reflectance claims on CRS-less can_tmr.hdr."""
    audit = audit_envi_dataset(
        SAMPLE_CAN_TMR_HDR,
        claimed_area_unit="km^2",
        claimed_calibrated_reflectance=True,
    )
    check_ids = {item["check_id"] for item in audit["issues"]}
    passed = (
        not audit["passed"]
        and "CHK-AUDIT-CRS-001" in check_ids
        and "CHK-AUDIT-SCALE-001" in check_ids
    )
    return {
        "scenario_id": "FAULT-02",
        "historical_case_id": "HIST-ERR-02",
        "check_id": "CHK-AUDIT-CRS-001",
        "passed": passed,
        "details": {"caught_check_ids": sorted(check_ids)},
    }


def fault_03_kt_third_component_mislabeling() -> dict[str, Any]:
    """FAULT-03: Inject 'Wetness' without 'Third' on Landsat 5 TM K-T transform."""
    cube = [[[10 + b + x + y for x in range(3)] for y in range(3)] for b in range(6)]
    caught = False
    try:
        compute_tasseled_cap_tm(cube, third_component_label="Calibrated Absolute Wetness")
    except ValueError as exc:
        caught = "CHK-SPEC-KT-THIRD-001" in str(exc)
    return {
        "scenario_id": "FAULT-03",
        "historical_case_id": "HIST-ERR-03",
        "check_id": "CHK-SPEC-KT-THIRD-001",
        "passed": caught,
        "details": {"mislabeling_blocked": caught},
    }


def fault_04_pca_full_image_leakage_in_supervised_eval() -> dict[str, Any]:
    """FAULT-04: Inject full-image PCA fitting when for_supervised_evaluation=True."""
    cube = [[[10 + b * 2 + x + y for x in range(4)] for y in range(4)] for b in range(6)]
    caught = False
    try:
        compute_pca(
            cube,
            fit_domain="full_image_unsupervised",
            for_supervised_evaluation=True,
        )
    except ValueError as exc:
        caught = "CHK-SPEC-PCA-LEAK-001" in str(exc)
    return {
        "scenario_id": "FAULT-04",
        "historical_case_id": "HIST-ERR-04",
        "check_id": "CHK-SPEC-PCA-LEAK-001",
        "passed": caught,
        "details": {"pca_leakage_blocked": caught},
    }


def fault_05_categorical_bilinear_resampling() -> dict[str, Any]:
    """FAULT-05: Inject bilinear resampling on a categorical classification map."""
    cat_cube = [[[1, 1, 4, 4], [1, 1, 4, 4], [2, 2, 5, 5], [2, 2, 5, 5]]]
    caught = False
    try:
        resample_raster(cat_cube, target_height=2, target_width=2, interpolation="bilinear", is_categorical=True)
    except ValueError as exc:
        caught = "CHK-PREPROC-RESAMPLE-CAT-001" in str(exc)
    return {
        "scenario_id": "FAULT-05",
        "historical_case_id": "HIST-ERR-05",
        "check_id": "CHK-PREPROC-RESAMPLE-CAT-001",
        "passed": caught,
        "details": {"categorical_bilinear_blocked": caught},
    }


def fault_06_spatial_buffer_and_diagnostic_overclaim() -> dict[str, Any]:
    """FAULT-06: Inject train/test points within 2 pixels (<5px buffer) claiming independent evaluation."""
    train_pts = [{"x": 10, "y": 10, "semantic_id": "cropland"}]
    test_pts = [{"x": 12, "y": 11, "semantic_id": "cropland"}]
    res_buf = audit_sample_split(
        train_pts,
        test_pts,
        min_buffer_pixels=5,
        claimed_evaluation_kind="buffered_independent_holdout",
    )
    res_diag = audit_sample_split(
        [{"x": 10, "y": 10, "semantic_id": "cropland"}],
        [{"x": 50, "y": 50, "semantic_id": "cropland"}],
        min_buffer_pixels=5,
        claimed_evaluation_kind="buffered_independent_holdout",
        is_diagnostic_revision=True,
    )
    passed = (
        not res_buf["passed"]
        and res_buf["actual_evaluation_kind"] == "spatially_contaminated_holdout"
        and not res_diag["passed"]
        and res_diag["actual_evaluation_kind"] == "diagnostic_holdout"
    )
    return {
        "scenario_id": "FAULT-06",
        "historical_case_id": "HIST-ERR-06",
        "check_id": "CHK-AUDIT-BUFFER-001",
        "passed": passed,
        "details": {
            "buffer_actual_kind": res_buf["actual_evaluation_kind"],
            "diagnostic_actual_kind": res_diag["actual_evaluation_kind"],
        },
    }


def fault_07_pa_ua_swap_and_unclassified_omission() -> dict[str, Any]:
    """FAULT-07: Inject transposed PA/UA values and omitted 0=Unclassified row totals."""
    schema = CANONICAL_CLASS_SCHEMAS["envi_ex8"]
    # Reference: 10 cropland (1), 10 forest (2)
    ref = [1] * 10 + [2] * 10
    # Predicted: 6 of cropland -> 1, 2 -> 2, 2 -> 0(unclassified); 9 of forest -> 2, 1 -> 1
    pred = [1] * 6 + [2] * 2 + [0] * 2 + [2] * 9 + [1] * 1
    ev = evaluate_classification(ref, pred, schema)
    # True cropland PA = 6/10 = 60.0%, UA = 6/7 = 85.71%, PA_no_unclass = 6/8 = 75.0%
    swap_res = detect_pa_ua_swap(
        ev,
        reported_pa_pct={"cropland": 85.71, "forest": 90.0},
        reported_ua_pct={"cropland": 60.0, "forest": 81.82},
    )
    omit_res = detect_pa_ua_swap(
        ev,
        reported_pa_pct={"cropland": 75.0, "forest": 90.0},
        reported_ua_pct={"cropland": 85.71, "forest": 81.82},
    )
    passed = (
        not swap_res["passed"]
        and "cropland" in swap_res["swapped_classes"]
        and not omit_res["passed"]
        and "cropland" in omit_res["omitted_unclassified_classes"]
    )
    return {
        "scenario_id": "FAULT-07",
        "historical_case_id": "HIST-ERR-07",
        "check_id": "CHK-EVAL-PA-UA-001",
        "passed": passed,
        "details": {
            "swapped_classes": swap_res["swapped_classes"],
            "omitted_unclassified_classes": omit_res["omitted_unclassified_classes"],
        },
    }


def fault_08_table_column_swap_and_water_loss() -> dict[str, Any]:
    """FAULT-08: Inject ENVI Ex8 Table 6 column swap (ML_Clump vs ML_Sieve) and narrow water erosion."""
    manifest_metrics = {
        "water": {"raw_ml": 134, "ml_clump": 93, "ml_sieve": 124},
        "built_up": {"raw_ml": 210, "ml_clump": 245, "ml_sieve": 215},
    }
    swapped_table = {
        "table_id": "postprocess_comparison",
        "columns": [
            {"column_id": "raw_ml", "bound_id": "raw_ml", "header": "ML 原图"},
            {"column_id": "ml_clump", "bound_id": "ml_clump", "header": "ML_Clump"},
            {"column_id": "ml_sieve", "bound_id": "ml_sieve", "header": "ML_Sieve"},
        ],
        "rows": [
            {
                "row_id": "water",
                "bound_row_id": "water",
                "cells": {"raw_ml": 134, "ml_clump": 124, "ml_sieve": 93},
            }
        ],
    }
    tbl_audit = audit_report_table(swapped_table, manifest_metrics)

    # Narrow 1-pixel water channel (code 5 in envi_ex8) surrounded by cropland (code 1)
    raw_map = [
        [1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1],
        [5, 5, 5, 5, 5],
        [1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1],
    ]
    maj_map = majority_filter(raw_map, window_size=3)
    post_eval = evaluate_postprocess_branches(
        raw_map,
        {"majority_3x3": maj_map},
        CANONICAL_CLASS_SCHEMAS["envi_ex8"],
        water_semantic_id="water",
        water_loss_threshold_pct=15.0,
    )
    passed = (
        not tbl_audit["passed"]
        and len(post_eval["water_loss_warnings"]) == 1
        and post_eval["branches"]["majority_3x3"]["water_loss_warning"]
    )
    return {
        "scenario_id": "FAULT-08",
        "historical_case_id": "HIST-ERR-08",
        "check_id": "CHK-REPORT-TABLE-COL-001",
        "passed": passed,
        "details": {
            "table_swap_caught": not tbl_audit["passed"],
            "water_loss_pct": post_eval["branches"]["majority_3x3"]["water_loss_pct"],
        },
    }


def fault_09_cross_software_class_code_collision() -> dict[str, Any]:
    """FAULT-09: Inject direct raw code comparison between MATLAB and ENVI Ex8 class schemas."""
    res = audit_class_mapping(
        CANONICAL_CLASS_SCHEMAS["matlab_archive"],
        CANONICAL_CLASS_SCHEMAS["envi_ex8"],
        allow_raw_code_comparison=True,
    )
    colliding_codes = [c["native_code"] for c in res["collisions"]]
    passed = not res["passed"] and colliding_codes == [3, 4, 5]
    return {
        "scenario_id": "FAULT-09",
        "historical_case_id": "HIST-ERR-09",
        "check_id": "CHK-CLASS-MAP-001",
        "passed": passed,
        "details": {"colliding_native_codes": colliding_codes, "bridge_a_to_b": res["bridge_a_to_b"]},
    }


def fault_10_isodata_degeneracy_and_headless_gui_fabrication() -> dict[str, Any]:
    """FAULT-10: Detect ISODATA 0-split/0-merge degeneracy, invalid PP policy, and fake GUI report wording."""
    cube = [[[10 + b + (x % 3) * 5 for x in range(6)] for y in range(6)] for b in range(4)]
    iso_res = isodata_classify(
        cube,
        k_init=3,
        k_min=3,
        k_max=6,
        max_iter=6,
        split_std_threshold=999.0,
        merge_distance_threshold=0.001,
    )
    caught_pp = False
    try:
        parallelepiped_classify(cube, {1: [[10, 11, 12, 13], [12, 13, 14, 15]]}, overlap_policy="silent_last_wins")
    except ValueError as exc:
        caught_pp = "CHK-CLASS-PP-001" in str(exc)

    rep_audit = audit_report_payload(
        {
            "sections": {
                "classification": "在本次实验中，我们点击菜单栏打开 Classification 对话框并在弹出的对话框中勾选参数。"
            }
        },
        {
            "run_id": "RUN-TEST-010",
            "execution_mode": "headless_api",
            "evaluation_kind": "reference_agreement",
            "has_crs": True,
            "has_verified_scale_factor": True,
        },
    )
    passed = (
        iso_res["degenerated_to_kmeans"] is True
        and caught_pp
        and not rep_audit["passed"]
        and any(i["check_id"] == "CHK-REPORT-HONESTY-001" for i in rep_audit["issues"])
    )
    return {
        "scenario_id": "FAULT-10",
        "historical_case_id": "HIST-ERR-10",
        "check_id": "CHK-CLASS-ISO-001",
        "passed": passed,
        "details": {
            "isodata_degenerated_to_kmeans": iso_res["degenerated_to_kmeans"],
            "invalid_parallelepiped_policy_blocked": caught_pp,
            "headless_gui_fabrication_blocked": not rep_audit["passed"],
        },
    }


def run_all_fault_scenarios() -> dict[str, Any]:
    """Execute all 10 mandatory fault-injection verification scenarios."""
    runners = [
        fault_01_uint8_underflow_and_zero_denom,
        fault_02_missing_crs_and_unverified_scale,
        fault_03_kt_third_component_mislabeling,
        fault_04_pca_full_image_leakage_in_supervised_eval,
        fault_05_categorical_bilinear_resampling,
        fault_06_spatial_buffer_and_diagnostic_overclaim,
        fault_07_pa_ua_swap_and_unclassified_omission,
        fault_08_table_column_swap_and_water_loss,
        fault_09_cross_software_class_code_collision,
        fault_10_isodata_degeneracy_and_headless_gui_fabrication,
    ]
    results = [fn() for fn in runners]
    passed_count = sum(1 for r in results if r["passed"])
    return {
        "total_scenarios": len(results),
        "passed_scenarios": passed_count,
        "all_passed": passed_count == len(results),
        "results": results,
    }
