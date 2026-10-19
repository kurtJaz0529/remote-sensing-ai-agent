"""Dataset, header, CRS/scale boundary, class schema, and spatial buffer auditor (T17)."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

ENVI_DTYPE_BYTES: dict[int, tuple[str, int]] = {
    1: ("uint8", 1),
    2: ("int16", 2),
    3: ("int32", 4),
    4: ("float32", 4),
    5: ("float64", 8),
    12: ("uint16", 2),
    13: ("uint32", 4),
    14: ("int64", 8),
    15: ("uint64", 8),
}

CANONICAL_CLASS_SCHEMAS: dict[str, dict[int, dict[str, str]]] = {
    "matlab_archive": {
        0: {"semantic_id": "unclassified", "name_zh": "未分类"},
        1: {"semantic_id": "cropland", "name_zh": "耕地"},
        2: {"semantic_id": "forest", "name_zh": "有林地"},
        3: {"semantic_id": "built_up", "name_zh": "建设用地"},
        4: {"semantic_id": "water", "name_zh": "水域"},
        5: {"semantic_id": "bare_land", "name_zh": "裸地"},
        6: {"semantic_id": "other", "name_zh": "其他"},
    },
    "envi_ex8": {
        0: {"semantic_id": "unclassified", "name_zh": "未分类"},
        1: {"semantic_id": "cropland", "name_zh": "耕地"},
        2: {"semantic_id": "forest", "name_zh": "有林地"},
        3: {"semantic_id": "bare_land", "name_zh": "裸地"},
        4: {"semantic_id": "built_up", "name_zh": "建设用地"},
        5: {"semantic_id": "water", "name_zh": "水域"},
        6: {"semantic_id": "other", "name_zh": "其他"},
    },
}

FORBIDDEN_METRIC_AREA_PATTERNS = (
    r"\bkm\^?2\b",
    r"\bha\b",
    r"\bhm\^?2\b",
    r"\bm\^?2\b",
    r"公顷",
    r"平方千米",
    r"平方公里",
    r"平方米",
)


def parse_envi_header(hdr_source: str | Path) -> dict[str, Any]:
    """Parse an ENVI .hdr text or file into normalized key-value pairs."""
    if isinstance(hdr_source, Path) or (
        isinstance(hdr_source, str) and "\n" not in hdr_source and Path(hdr_source).exists()
    ):
        text = Path(hdr_source).read_text(encoding="utf-8", errors="replace")
    else:
        text = str(hdr_source)

    raw_fields: dict[str, str] = {}
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or line.upper() == "ENVI" or line.startswith(";"):
            idx += 1
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip().lower()
            val = val.strip()
            if val.startswith("{"):
                brace_depth = val.count("{") - val.count("}")
                parts = [val]
                while brace_depth > 0 and idx + 1 < len(lines):
                    idx += 1
                    next_line = lines[idx].strip()
                    parts.append(next_line)
                    brace_depth += next_line.count("{") - next_line.count("}")
                val = " ".join(parts)
            raw_fields[key] = val
        idx += 1

    def _parse_brace_list(raw_val: str) -> list[str]:
        inner = raw_val.strip()
        if inner.startswith("{") and inner.endswith("}"):
            inner = inner[1:-1]
        return [item.strip() for item in inner.split(",") if item.strip()]

    samples = int(raw_fields.get("samples", "0") or 0)
    n_lines = int(raw_fields.get("lines", "0") or 0)
    bands = int(raw_fields.get("bands", "0") or 0)
    data_type = int(raw_fields.get("data type", "0") or 0)
    header_offset = int(raw_fields.get("header offset", "0") or 0)
    interleave = raw_fields.get("interleave", "").lower()
    byte_order = int(raw_fields.get("byte order", "0") or 0)

    dtype_name, bytes_per_value = ENVI_DTYPE_BYTES.get(data_type, ("unknown", 0))
    map_info = raw_fields.get("map info", "")
    crs_string = raw_fields.get("coordinate system string", "")
    has_crs = bool(map_info.strip("{}").strip() or crs_string.strip("{}").strip())

    scale_factor_raw = raw_fields.get("reflectance scale factor", "") or raw_fields.get(
        "data gain values", ""
    )
    has_verified_scale_factor = bool(scale_factor_raw.strip("{}").strip())

    band_names = _parse_brace_list(raw_fields["band names"]) if "band names" in raw_fields else []
    wavelengths = (
        [float(x) for x in _parse_brace_list(raw_fields["wavelength"])]
        if "wavelength" in raw_fields
        else []
    )

    return {
        "samples": samples,
        "lines": n_lines,
        "bands": bands,
        "data_type": data_type,
        "dtype_name": dtype_name,
        "bytes_per_value": bytes_per_value,
        "header_offset": header_offset,
        "interleave": interleave,
        "byte_order": byte_order,
        "has_crs": has_crs,
        "map_info": map_info,
        "coordinate_system_string": crs_string,
        "has_verified_scale_factor": has_verified_scale_factor,
        "scale_factor_raw": scale_factor_raw,
        "band_names": band_names,
        "wavelengths": wavelengths,
        "expected_binary_bytes": samples * n_lines * bands * bytes_per_value + header_offset,
        "raw_fields": raw_fields,
    }


def audit_envi_dataset(
    hdr_source: str | Path,
    img_path: str | Path | None = None,
    observed_min: float | None = None,
    observed_max: float | None = None,
    claimed_area_unit: str | None = None,
    claimed_calibrated_reflectance: bool = False,
) -> dict[str, Any]:
    """Audit ENVI dataset header, binary size, CRS boundary, and reflectance scale claims."""
    meta = parse_envi_header(hdr_source)
    issues: list[dict[str, str]] = []
    warnings: list[str] = []

    if meta["samples"] <= 0 or meta["lines"] <= 0 or meta["bands"] <= 0:
        issues.append(
            {
                "check_id": "CHK-AUDIT-HDR-001",
                "severity": "error",
                "message": "Invalid ENVI dimensions: samples, lines, and bands must be positive.",
            }
        )
    if meta["interleave"] not in ("bsq", "bil", "bip"):
        issues.append(
            {
                "check_id": "CHK-AUDIT-HDR-001",
                "severity": "error",
                "message": f"Unsupported ENVI interleave: {meta['interleave']!r}.",
            }
        )
    if meta["bytes_per_value"] == 0:
        issues.append(
            {
                "check_id": "CHK-AUDIT-HDR-001",
                "severity": "error",
                "message": f"Unsupported ENVI data type code: {meta['data_type']}.",
            }
        )

    if img_path is not None:
        p = Path(img_path)
        if not p.exists():
            issues.append(
                {
                    "check_id": "CHK-AUDIT-HDR-001",
                    "severity": "error",
                    "message": f"Binary raster file does not exist: {p}",
                }
            )
        else:
            actual_bytes = p.stat().st_size
            if actual_bytes != meta["expected_binary_bytes"]:
                issues.append(
                    {
                        "check_id": "CHK-AUDIT-HDR-001",
                        "severity": "error",
                        "message": (
                            f"Binary size mismatch: expected {meta['expected_binary_bytes']} bytes "
                            f"from .hdr, got {actual_bytes} bytes."
                        ),
                    }
                )

    allowed_area_units = ["pixel", "pixel^2", "px", "px^2"]
    if meta["has_crs"]:
        allowed_area_units.extend(["m^2", "hm^2", "ha", "km^2"])
    else:
        warnings.append(
            "Header lacks 'map info' / CRS: only pixel coordinates and pixel^2 area units are permitted."
        )
        if claimed_area_unit:
            for pattern in FORBIDDEN_METRIC_AREA_PATTERNS:
                if re.search(pattern, claimed_area_unit, flags=re.IGNORECASE):
                    issues.append(
                        {
                            "check_id": "CHK-AUDIT-CRS-001",
                            "severity": "error",
                            "message": (
                                f"Dataset lacks CRS ('map info' absent), so physical area unit "
                                f"{claimed_area_unit!r} is prohibited; use 'pixel' or 'pixel^2'."
                            ),
                        }
                    )
                    break

    if not meta["has_verified_scale_factor"]:
        warnings.append(
            "No verified reflectance scale factor in .hdr: report stored digital values (e.g., 0..100) only."
        )
        if claimed_calibrated_reflectance:
            issues.append(
                {
                    "check_id": "CHK-AUDIT-SCALE-001",
                    "severity": "error",
                    "message": (
                        "Header lacks verified reflectance scale factor; claiming calibrated 0..1 "
                        "surface reflectance is prohibited."
                    ),
                }
            )

    value_range_summary = None
    if observed_min is not None and observed_max is not None:
        value_range_summary = {
            "observed_min": float(observed_min),
            "observed_max": float(observed_max),
            "is_scaled_0_100_uint8": bool(
                meta["dtype_name"] == "uint8" and 0.0 <= observed_min and observed_max <= 100.0
            ),
        }

    return {
        "passed": len(issues) == 0,
        "metadata": meta,
        "allowed_area_units": allowed_area_units,
        "value_range_summary": value_range_summary,
        "warnings": warnings,
        "issues": issues,
    }


def audit_class_mapping(
    schema_a: Mapping[int, Mapping[str, str]],
    schema_b: Mapping[int, Mapping[str, str]],
    allow_raw_code_comparison: bool = False,
) -> dict[str, Any]:
    """Check whether two class code schemas collide in raw integer codes and build a bridge."""
    collisions: list[dict[str, Any]] = []
    bridge_a_to_b: dict[int, int] = {}
    semantic_to_b = {info["semantic_id"]: int(code) for code, info in schema_b.items()}

    for code_a, info_a in sorted(schema_a.items()):
        code_int = int(code_a)
        sem_a = info_a["semantic_id"]
        if sem_a in semantic_to_b:
            bridge_a_to_b[code_int] = semantic_to_b[sem_a]
        if code_int in schema_b:
            sem_b = schema_b[code_int]["semantic_id"]
            if sem_a != sem_b:
                collisions.append(
                    {
                        "native_code": code_int,
                        "schema_a_semantic_id": sem_a,
                        "schema_a_name": info_a.get("name_zh", sem_a),
                        "schema_b_semantic_id": sem_b,
                        "schema_b_name": schema_b[code_int].get("name_zh", sem_b),
                    }
                )

    issues: list[dict[str, str]] = []
    if collisions and allow_raw_code_comparison:
        issues.append(
            {
                "check_id": "CHK-CLASS-MAP-001",
                "severity": "error",
                "message": (
                    f"Direct raw integer class code comparison is blocked: {len(collisions)} "
                    f"class codes have conflicting semantics across schemas."
                ),
            }
        )

    return {
        "passed": len(issues) == 0,
        "has_code_collision": len(collisions) > 0,
        "collisions": collisions,
        "bridge_a_to_b": bridge_a_to_b,
        "issues": issues,
    }


def audit_sample_split(
    train_points: Sequence[Mapping[str, Any]],
    test_points: Sequence[Mapping[str, Any]],
    min_buffer_pixels: int = 5,
    claimed_evaluation_kind: str = "buffered_independent_holdout",
    is_diagnostic_revision: bool = False,
    is_visual_reference_only: bool = False,
) -> dict[str, Any]:
    """Audit spatial overlap, Chebyshev buffer distance, and evaluation_kind honesty."""
    overlap_coords: list[tuple[int, int]] = []
    buffer_violations: list[dict[str, Any]] = []
    min_chebyshev: float = math.inf

    train_coords = [(int(p["x"]), int(p["y"]), str(p.get("semantic_id", ""))) for p in train_points]
    test_coords = [(int(p["x"]), int(p["y"]), str(p.get("semantic_id", ""))) for p in test_points]

    train_xy_set = {(x, y) for x, y, _ in train_coords}
    for tx, ty, _ in test_coords:
        if (tx, ty) in train_xy_set:
            overlap_coords.append((tx, ty))
        for rx, ry, _ in train_coords:
            dist = max(abs(tx - rx), abs(ty - ry))
            if dist < min_chebyshev:
                min_chebyshev = float(dist)
            if 0 < dist < min_buffer_pixels:
                buffer_violations.append(
                    {"test_xy": [tx, ty], "train_xy": [rx, ry], "chebyshev_distance": dist}
                )

    if overlap_coords and len(overlap_coords) == len(test_coords):
        actual_kind = "resubstitution"
    elif overlap_coords or buffer_violations:
        actual_kind = "spatially_contaminated_holdout"
    elif is_diagnostic_revision:
        actual_kind = "diagnostic_holdout"
    elif is_visual_reference_only:
        actual_kind = "reference_agreement"
    else:
        actual_kind = "buffered_independent_holdout"

    issues: list[dict[str, str]] = []
    if claimed_evaluation_kind in ("independent", "buffered_independent_holdout"):
        if actual_kind != "buffered_independent_holdout":
            check_id = (
                "CHK-AUDIT-BUFFER-001"
                if (overlap_coords or buffer_violations)
                else "CHK-EVAL-KIND-001"
            )
            issues.append(
                {
                    "check_id": check_id,
                    "severity": "error",
                    "message": (
                        f"Claimed evaluation_kind={claimed_evaluation_kind!r} is invalid; "
                        f"actual sample audit determined evaluation_kind={actual_kind!r} "
                        f"(overlap={len(overlap_coords)}, buffer_violations={len(buffer_violations)}, "
                        f"is_diagnostic_revision={is_diagnostic_revision}, "
                        f"is_visual_reference_only={is_visual_reference_only})."
                    ),
                }
            )

    return {
        "passed": len(issues) == 0,
        "claimed_evaluation_kind": claimed_evaluation_kind,
        "actual_evaluation_kind": actual_kind,
        "overlap_count": len(overlap_coords),
        "buffer_violation_count": len(buffer_violations),
        "min_chebyshev_distance": None if math.isinf(min_chebyshev) else min_chebyshev,
        "min_buffer_pixels_required": min_buffer_pixels,
        "issues": issues,
    }
