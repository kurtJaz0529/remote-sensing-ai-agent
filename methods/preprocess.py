"""Raster preprocessing package: crop, reprojection check, resampling guard, and band stacking (T18)."""
from __future__ import annotations

import math
from typing import Any, Sequence


def validate_cube_shape(cube: Sequence[Sequence[Sequence[float | int]]]) -> tuple[int, int, int]:
    """Validate a 3D raster cube [bands][height][width] and return (B, H, W)."""
    if not cube or not cube[0] or not cube[0][0]:
        raise ValueError("CHK-PREPROC-CROP-001: Raster cube must have non-zero [bands][height][width]")
    bands = len(cube)
    height = len(cube[0])
    width = len(cube[0][0])
    for b_idx, band in enumerate(cube):
        if len(band) != height:
            raise ValueError(f"CHK-PREPROC-STACK-001: Band {b_idx} height mismatch ({len(band)} != {height})")
        for r_idx, row in enumerate(band):
            if len(row) != width:
                raise ValueError(
                    f"CHK-PREPROC-STACK-001: Band {b_idx} row {r_idx} width mismatch ({len(row)} != {width})"
                )
    return bands, height, width


def crop_raster(
    cube: Sequence[Sequence[Sequence[float | int]]],
    y_start: int,
    y_end: int,
    x_start: int,
    x_end: int,
) -> dict[str, Any]:
    """Crop a 3D raster cube [B][H][W] to [y_start:y_end, x_start:x_end] in pixel coordinates."""
    bands, height, width = validate_cube_shape(cube)
    if not (0 <= y_start < y_end <= height and 0 <= x_start < x_end <= width):
        raise ValueError(
            f"CHK-PREPROC-CROP-001: Invalid crop bounds y=[{y_start},{y_end}), x=[{x_start},{x_end}) "
            f"for raster of shape (H={height}, W={width})"
        )
    cropped = [
        [[ band[y][x] for x in range(x_start, x_end) ] for y in range(y_start, y_end)]
        for band in cube
    ]
    return {
        "cube": cropped,
        "bands": bands,
        "height": y_end - y_start,
        "width": x_end - x_start,
        "crop_window": {"y_start": y_start, "y_end": y_end, "x_start": x_start, "x_end": x_end},
    }


def resample_raster(
    cube: Sequence[Sequence[Sequence[float | int]]],
    target_height: int,
    target_width: int,
    interpolation: str = "nearest",
    is_categorical: bool = False,
) -> dict[str, Any]:
    """Resample a 3D raster cube; strictly blocks bilinear/cubic on categorical rasters."""
    bands, src_h, src_w = validate_cube_shape(cube)
    if target_height <= 0 or target_width <= 0:
        raise ValueError("CHK-PREPROC-RESAMPLE-CAT-001: target_height and target_width must be positive")

    interp = interpolation.strip().lower()
    if interp not in ("nearest", "bilinear", "cubic"):
        raise ValueError(f"Unsupported interpolation method: {interpolation!r}")

    if is_categorical and interp != "nearest":
        raise ValueError(
            f"CHK-PREPROC-RESAMPLE-CAT-001: Categorical raster or ROI mask cannot use "
            f"interpolation={interpolation!r}; only 'nearest' is permitted to prevent fabricated class codes."
        )

    out_cube: list[list[list[float | int]]] = []
    for b in range(bands):
        src_band = cube[b]
        out_band: list[list[float | int]] = []
        for ty in range(target_height):
            sy = ((ty + 0.5) * src_h / target_height) - 0.5
            out_row: list[float | int] = []
            for tx in range(target_width):
                sx = ((tx + 0.5) * src_w / target_width) - 0.5
                if interp == "nearest":
                    ny = min(max(int(math.floor(sy + 0.5)), 0), src_h - 1)
                    nx = min(max(int(math.floor(sx + 0.5)), 0), src_w - 1)
                    val = src_band[ny][nx]
                    out_row.append(int(val) if is_categorical else val)
                else:
                    y0 = min(max(int(math.floor(sy)), 0), src_h - 1)
                    y1 = min(max(y0 + 1, 0), src_h - 1)
                    x0 = min(max(int(math.floor(sx)), 0), src_w - 1)
                    x1 = min(max(x0 + 1, 0), src_w - 1)
                    wy = max(0.0, min(1.0, sy - math.floor(sy)))
                    wx = max(0.0, min(1.0, sx - math.floor(sx)))
                    v00 = float(src_band[y0][x0])
                    v01 = float(src_band[y0][x1])
                    v10 = float(src_band[y1][x0])
                    v11 = float(src_band[y1][x1])
                    val_f = (
                        (1.0 - wy) * ((1.0 - wx) * v00 + wx * v01)
                        + wy * ((1.0 - wx) * v10 + wx * v11)
                    )
                    out_row.append(round(val_f, 6))
            out_band.append(out_row)
        out_cube.append(out_band)

    return {
        "cube": out_cube,
        "bands": bands,
        "height": target_height,
        "width": target_width,
        "interpolation": interp,
        "is_categorical": is_categorical,
    }


def stack_bands(
    band_layers: Sequence[Sequence[Sequence[float | int]]],
    band_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Stack 2D band layers [H][W] into a 3D cube [B][H][W] after verifying spatial alignment."""
    bands, height, width = validate_cube_shape(band_layers)
    names = list(band_names) if band_names is not None else [f"band_{i+1}" for i in range(bands)]
    if len(names) != bands:
        raise ValueError("CHK-PREPROC-STACK-001: band_names length must match number of band layers")
    return {
        "cube": [[[val for val in row] for row in band] for band in band_layers],
        "bands": bands,
        "height": height,
        "width": width,
        "band_names": names,
    }


def validate_reprojection_request(
    has_source_crs: bool,
    source_crs: str | None,
    target_crs: str | None,
    software: str = "ArcGISPro",
    available_licenses: Sequence[str] = ("ArcGISPro",),
) -> dict[str, Any]:
    """Validate whether a CRS reprojection request is physically and license-wise valid."""
    if not has_source_crs or not (source_crs or "").strip():
        raise ValueError(
            "CHK-AUDIT-CRS-001: Cannot reproject raster without source CRS ('map info' is missing)."
        )
    if not (target_crs or "").strip():
        raise ValueError("Target CRS must be non-empty for reprojection.")
    if software == "MATLAB" and "Map_Toolbox" not in set(available_licenses):
        raise ValueError(
            "CHK-RETRIEVAL-LICENSE-001: Local MATLAB lacks Mapping Toolbox; route CRS reprojection to ArcGISPro or ENVI."
        )
    return {
        "passed": True,
        "source_crs": source_crs,
        "target_crs": target_crs,
        "routed_software": software,
    }
