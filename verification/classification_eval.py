"""Independent classification accuracy, PA/UA swap detection, and vector roundtrip verifier (T22)."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Mapping, Sequence


def evaluate_classification(
    reference_labels: Sequence[int | str],
    predicted_labels: Sequence[int | str],
    reference_schema: Mapping[int, Mapping[str, str]],
    predicted_schema: Mapping[int, Mapping[str, str]] | None = None,
    ordered_semantic_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compute C x (C+1) asymmetric confusion matrix, OA, Kappa, PA, UA, and unclassified rate.

    Rows represent reference ground-truth semantic classes (1..C).
    Columns represent predicted semantic classes (1..C) plus a final 'unclassified' column.
    """
    if len(reference_labels) != len(predicted_labels) or len(reference_labels) == 0:
        raise ValueError("reference_labels and predicted_labels must have equal non-zero length")

    pred_schema = predicted_schema or reference_schema

    def _to_semantic(val: int | str, schema: Mapping[int, Mapping[str, str]]) -> str:
        if isinstance(val, str) and not val.isdigit():
            return val
        code = int(val)
        if code == 0:
            return "unclassified"
        if code not in schema:
            raise ValueError(f"Unknown class code {code} in schema")
        return schema[code]["semantic_id"]

    ref_sem = [_to_semantic(r, reference_schema) for r in reference_labels]
    pred_sem = [_to_semantic(p, pred_schema) for p in predicted_labels]

    if ordered_semantic_ids is None:
        ordered_semantic_ids = [
            info["semantic_id"]
            for code, info in sorted(reference_schema.items())
            if int(code) != 0 and info["semantic_id"] != "unclassified"
        ]
    else:
        ordered_semantic_ids = [s for s in ordered_semantic_ids if s != "unclassified"]

    row_classes = list(ordered_semantic_ids)
    col_classes = list(ordered_semantic_ids) + ["unclassified"]
    row_index = {sem: idx for idx, sem in enumerate(row_classes)}
    col_index = {sem: idx for idx, sem in enumerate(col_classes)}

    c_len = len(row_classes)
    matrix = [[0 for _ in range(c_len + 1)] for _ in range(c_len)]

    for r_label, p_label in zip(ref_sem, pred_sem):
        if r_label not in row_index:
            raise ValueError(f"Reference label {r_label!r} must be a valid non-unclassified class")
        r_idx = row_index[r_label]
        c_idx = col_index.get(p_label, c_len)
        matrix[r_idx][c_idx] += 1

    total_samples = len(ref_sem)
    row_totals = [sum(matrix[i]) for i in range(c_len)]
    col_totals = [sum(matrix[i][j] for i in range(c_len)) for j in range(c_len + 1)]
    diagonal_sum = sum(matrix[i][i] for i in range(c_len))
    unclassified_count = col_totals[c_len]

    overall_accuracy = diagonal_sum / total_samples if total_samples > 0 else 0.0

    # Expected agreement for Cohen's Kappa across the C classes (unclassified has 0 reference row total)
    pe = (
        sum(row_totals[i] * col_totals[i] for i in range(c_len)) / float(total_samples * total_samples)
        if total_samples > 0
        else 0.0
    )
    kappa = (overall_accuracy - pe) / (1.0 - pe) if abs(1.0 - pe) > 1e-12 else 0.0

    per_class: dict[str, dict[str, float | int]] = {}
    for i, sem_id in enumerate(row_classes):
        tp = matrix[i][i]
        r_tot = row_totals[i]
        c_tot = col_totals[i]
        unclass_in_row = matrix[i][c_len]
        pa = tp / r_tot if r_tot > 0 else 0.0
        pa_ignoring_unclassified = (
            tp / (r_tot - unclass_in_row) if (r_tot - unclass_in_row) > 0 else 0.0
        )
        ua = tp / c_tot if c_tot > 0 else 0.0
        per_class[sem_id] = {
            "reference_total": r_tot,
            "classified_total": c_tot,
            "true_positive": tp,
            "unclassified_omission": unclass_in_row,
            "producers_accuracy": round(pa, 6),
            "producers_accuracy_pct": round(pa * 100.0, 2),
            "producers_accuracy_ignoring_unclassified_pct": round(
                pa_ignoring_unclassified * 100.0, 2
            ),
            "users_accuracy": round(ua, 6),
            "users_accuracy_pct": round(ua * 100.0, 2),
            "omission_error_pct": round((1.0 - pa) * 100.0, 2),
            "commission_error_pct": round((1.0 - ua) * 100.0, 2),
        }

    return {
        "row_classes": row_classes,
        "col_classes": col_classes,
        "matrix": matrix,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "total_samples": total_samples,
        "overall_accuracy": round(overall_accuracy, 6),
        "overall_accuracy_pct": round(overall_accuracy * 100.0, 2),
        "kappa": round(kappa, 6),
        "unclassified_count": unclassified_count,
        "unclassified_rate": round(unclassified_count / total_samples, 6),
        "unclassified_rate_pct": round(unclassified_count / total_samples * 100.0, 2),
        "per_class": per_class,
    }


def detect_pa_ua_swap(
    eval_result: Mapping[str, Any],
    reported_pa_pct: Mapping[str, float],
    reported_ua_pct: Mapping[str, float],
    tolerance_pct: float = 0.25,
) -> dict[str, Any]:
    """Detect whether reported PA/UA values are swapped or omitted the 0=Unclassified column."""
    per_class = eval_result["per_class"]
    swapped_classes: list[str] = []
    omitted_unclassified_classes: list[str] = []
    mismatched_classes: list[str] = []

    for sem_id, stats in per_class.items():
        if sem_id not in reported_pa_pct or sem_id not in reported_ua_pct:
            continue
        rep_pa = float(reported_pa_pct[sem_id])
        rep_ua = float(reported_ua_pct[sem_id])
        true_pa = float(stats["producers_accuracy_pct"])
        true_ua = float(stats["users_accuracy_pct"])
        pa_no_unclass = float(stats["producers_accuracy_ignoring_unclassified_pct"])

        pa_matches = abs(rep_pa - true_pa) <= tolerance_pct
        ua_matches = abs(rep_ua - true_ua) <= tolerance_pct

        if not (pa_matches and ua_matches):
            if (
                abs(rep_pa - true_ua) <= tolerance_pct
                and abs(rep_ua - true_pa) <= tolerance_pct
                and abs(true_pa - true_ua) > tolerance_pct
            ):
                swapped_classes.append(sem_id)
            elif (
                abs(rep_pa - pa_no_unclass) <= tolerance_pct
                and abs(pa_no_unclass - true_pa) > tolerance_pct
            ):
                omitted_unclassified_classes.append(sem_id)
            else:
                mismatched_classes.append(sem_id)

    issues: list[dict[str, str]] = []
    if swapped_classes:
        issues.append(
            {
                "check_id": "CHK-EVAL-PA-UA-001",
                "severity": "error",
                "message": (
                    f"Producer's Accuracy (PA) and User's Accuracy (UA) are transposed for classes: "
                    f"{swapped_classes}."
                ),
            }
        )
    if omitted_unclassified_classes:
        issues.append(
            {
                "check_id": "CHK-EVAL-PA-UA-001",
                "severity": "error",
                "message": (
                    f"Reported PA omitted 0=Unclassified pixels from reference row totals for classes: "
                    f"{omitted_unclassified_classes}."
                ),
            }
        )
    if mismatched_classes:
        issues.append(
            {
                "check_id": "CHK-EVAL-PA-UA-001",
                "severity": "error",
                "message": f"Reported PA/UA values do not match confusion matrix for: {mismatched_classes}.",
            }
        )

    return {
        "passed": len(issues) == 0,
        "swapped_classes": swapped_classes,
        "omitted_unclassified_classes": omitted_unclassified_classes,
        "mismatched_classes": mismatched_classes,
        "issues": issues,
    }


def read_shp_header(shp_path: str | Path) -> dict[str, Any]:
    """Read standard ESRI Shapefile (.shp) 100-byte binary header."""
    data = Path(shp_path).read_bytes()
    if len(data) < 100:
        raise ValueError("Shapefile (.shp) is shorter than 100-byte header")
    file_code = struct.unpack(">i", data[0:4])[0]
    file_length_words = struct.unpack(">i", data[24:28])[0]
    version, shape_type = struct.unpack("<ii", data[28:36])
    xmin, ymin, xmax, ymax = struct.unpack("<dddd", data[36:68])
    return {
        "file_code": file_code,
        "file_length_bytes": file_length_words * 2,
        "version": version,
        "shape_type": shape_type,
        "bbox": [xmin, ymin, xmax, ymax],
    }


def read_dbf_records(dbf_path: str | Path) -> list[dict[str, Any]]:
    """Read standard dBASE III+ (.dbf) attribute table records without third-party dependencies."""
    data = Path(dbf_path).read_bytes()
    if len(data) < 32:
        raise ValueError("DBF file is shorter than 32-byte header")
    num_records, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields: list[tuple[str, str, int, int]] = []
    offset = 32
    while offset < header_len - 1 and data[offset] != 0x0D:
        field_desc = data[offset : offset + 32]
        name = field_desc[0:11].split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        ftype = chr(field_desc[11])
        flen = field_desc[16]
        fdec = field_desc[17]
        fields.append((name, ftype, flen, fdec))
        offset += 32

    records: list[dict[str, Any]] = []
    pos = header_len
    for _ in range(num_records):
        if pos + record_len > len(data):
            break
        rec_bytes = data[pos : pos + record_len]
        pos += record_len
        if rec_bytes[0:1] == b"*":
            continue
        f_pos = 1
        row: dict[str, Any] = {}
        for name, ftype, flen, fdec in fields:
            raw_val = rec_bytes[f_pos : f_pos + flen].decode("utf-8", errors="replace").strip()
            f_pos += flen
            if ftype in ("N", "F"):
                if not raw_val:
                    row[name] = 0
                elif fdec > 0 or "." in raw_val:
                    row[name] = float(raw_val)
                else:
                    row[name] = int(raw_val)
            else:
                row[name] = raw_val
        records.append(row)
    return records


def audit_vector_raster_consistency(
    raster_class_pixel_counts: Mapping[int, int],
    vector_records: Sequence[Mapping[str, Any]],
    code_field: str = "GRIDCODE",
    area_field: str = "PIXEL_CNT",
) -> dict[str, Any]:
    """Verify that polygon vector export (.shp/.dbf) aggregates match raster class pixel counts."""
    vector_totals: dict[int, int] = {}
    for row in vector_records:
        code = int(row[code_field])
        count = int(round(float(row.get(area_field, 0))))
        vector_totals[code] = vector_totals.get(code, 0) + count

    discrepancies: list[dict[str, int]] = []
    all_codes = sorted(set(int(k) for k in raster_class_pixel_counts.keys()) | set(vector_totals.keys()))
    for code in all_codes:
        r_cnt = int(raster_class_pixel_counts.get(code, 0))
        v_cnt = int(vector_totals.get(code, 0))
        if r_cnt != v_cnt:
            discrepancies.append(
                {
                    "class_code": code,
                    "raster_pixel_count": r_cnt,
                    "vector_pixel_count": v_cnt,
                    "delta": v_cnt - r_cnt,
                }
            )

    issues: list[dict[str, str]] = []
    if discrepancies:
        issues.append(
            {
                "check_id": "CHK-EVAL-VEC-ROUNDTRIP-001",
                "severity": "error",
                "message": (
                    f"Vector-raster class pixel count mismatch across {len(discrepancies)} class(es): "
                    f"{discrepancies}"
                ),
            }
        )

    return {
        "passed": len(issues) == 0,
        "raster_totals": {int(k): int(v) for k, v in raster_class_pixel_counts.items()},
        "vector_totals": vector_totals,
        "discrepancies": discrepancies,
        "issues": issues,
    }
