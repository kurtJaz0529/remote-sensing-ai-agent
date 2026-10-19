"""Spectral indices (float64 cast + zero-denom mask), domain-isolated PCA, and Landsat 5 TM K-T transform (T19)."""
from __future__ import annotations

import math
from typing import Any, Sequence

from methods.preprocess import validate_cube_shape

# Crist & Cicone (1984) / standard 6-band Landsat 5 TM Tasseled Cap coefficients (TM1, TM2, TM3, TM4, TM5, TM7)
LANDSAT5_TM_KT_COEFFICIENTS: dict[str, tuple[float, float, float, float, float, float]] = {
    "Brightness": (0.2909, 0.2493, 0.4806, 0.5568, 0.4438, 0.1706),
    "Greenness": (-0.2728, -0.2174, -0.5508, 0.7221, 0.0733, -0.1648),
    "Third (Wetness-related)": (0.1446, 0.1761, 0.3322, 0.3396, -0.6210, -0.4186),
}


def compute_normalized_difference(
    band_a: Sequence[Sequence[float | int]],
    band_b: Sequence[Sequence[float | int]],
    nodata: float = -9999.0,
    eps: float = 1e-12,
    enforce_float64: bool = True,
) -> dict[str, Any]:
    """Compute (band_a - band_b) / (band_a + band_b) in float64 with explicit zero-denominator mask."""
    if not enforce_float64:
        raise ValueError(
            "CHK-SPEC-FLOAT-001: Spectral index calculation must cast inputs to float64 to prevent uint8 underflow."
        )
    _, height, width = validate_cube_shape([band_a, band_b])
    index_map: list[list[float]] = []
    zero_mask: list[list[int]] = []
    zero_count = 0
    valid_vals: list[float] = []

    for y in range(height):
        row_out: list[float] = []
        row_mask: list[int] = []
        for x in range(width):
            a = float(band_a[y][x])
            b = float(band_b[y][x])
            denom = a + b
            if abs(denom) <= eps:
                row_out.append(float(nodata))
                row_mask.append(1)
                zero_count += 1
            else:
                val = (a - b) / denom
                row_out.append(round(val, 6))
                row_mask.append(0)
                valid_vals.append(val)
        index_map.append(row_out)
        zero_mask.append(row_mask)

    return {
        "index_map": index_map,
        "zero_denominator_mask": zero_mask,
        "zero_denominator_count": zero_count,
        "nodata": float(nodata),
        "dtype": "float64",
        "valid_min": round(min(valid_vals), 6) if valid_vals else None,
        "valid_max": round(max(valid_vals), 6) if valid_vals else None,
    }


def compute_ndvi(
    nir_band: Sequence[Sequence[float | int]],
    red_band: Sequence[Sequence[float | int]],
    nodata: float = -9999.0,
) -> dict[str, Any]:
    res = compute_normalized_difference(nir_band, red_band, nodata=nodata)
    res["index_name"] = "NDVI"
    return res


def compute_ndwi(
    green_band: Sequence[Sequence[float | int]],
    nir_band: Sequence[Sequence[float | int]],
    nodata: float = -9999.0,
) -> dict[str, Any]:
    res = compute_normalized_difference(green_band, nir_band, nodata=nodata)
    res["index_name"] = "NDWI"
    return res


def compute_mndwi(
    green_band: Sequence[Sequence[float | int]],
    swir1_band: Sequence[Sequence[float | int]],
    nodata: float = -9999.0,
) -> dict[str, Any]:
    res = compute_normalized_difference(green_band, swir1_band, nodata=nodata)
    res["index_name"] = "MNDWI"
    return res


def _jacobi_eigen_symmetric(matrix: list[list[float]], max_sweeps: int = 100, tol: float = 1e-12) -> tuple[list[float], list[list[float]]]:
    """Deterministic Jacobi eigenvalue solver for real symmetric matrices in pure Python."""
    n = len(matrix)
    a = [[float(matrix[i][j]) for j in range(n)] for i in range(n)]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    for _ in range(max_sweeps):
        max_val = 0.0
        p, q = 0, 1
        for i in range(n):
            for j in range(i + 1, n):
                if abs(a[i][j]) > max_val:
                    max_val = abs(a[i][j])
                    p, q = i, j
        if max_val <= tol:
            break
        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]
        tau = (aqq - app) / (2.0 * apq)
        t = (1.0 if tau >= 0 else -1.0) / (abs(tau) + math.sqrt(1.0 + tau * tau))
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c

        a[p][p] = app - t * apq
        a[q][q] = aqq + t * apq
        a[p][q] = 0.0
        a[q][p] = 0.0
        for k in range(n):
            if k != p and k != q:
                akp = a[k][p]
                akq = a[k][q]
                a[k][p] = c * akp - s * akq
                a[p][k] = a[k][p]
                a[k][q] = s * akp + c * akq
                a[q][k] = a[k][q]
            vkp = v[k][p]
            vkq = v[k][q]
            v[k][p] = c * vkp - s * vkq
            v[k][q] = s * vkp + c * vkq

    eigenvalues = [a[i][i] for i in range(n)]
    # Columns of v are eigenvectors; sort descending by eigenvalue
    order = sorted(range(n), key=lambda idx: eigenvalues[idx], reverse=True)
    sorted_vals = [max(0.0, eigenvalues[idx]) for idx in order]
    sorted_vecs: list[list[float]] = []
    for idx in order:
        vec = [v[row][idx] for row in range(n)]
        # Enforce deterministic sign convention: first non-zero element positive
        for comp in vec:
            if abs(comp) > 1e-9:
                if comp < 0:
                    vec = [-x for x in vec]
                break
        sorted_vecs.append(vec)
    return sorted_vals, sorted_vecs


def compute_pca(
    cube: Sequence[Sequence[Sequence[float | int]]],
    fit_domain: str = "full_image_unsupervised",
    train_pixel_coords: Sequence[tuple[int, int]] | None = None,
    for_supervised_evaluation: bool = False,
    n_components: int | None = None,
) -> dict[str, Any]:
    """Compute Principal Component Analysis with strict train/test fit-domain isolation."""
    bands, height, width = validate_cube_shape(cube)
    if fit_domain not in ("full_image_unsupervised", "train_split_only"):
        raise ValueError(f"Invalid fit_domain: {fit_domain!r}")

    if for_supervised_evaluation and fit_domain != "train_split_only":
        raise ValueError(
            "CHK-SPEC-PCA-LEAK-001: PCA features used for supervised accuracy evaluation must set "
            "fit_domain='train_split_only' to prevent test-set variance leakage."
        )

    fit_vectors: list[list[float]] = []
    if fit_domain == "train_split_only":
        if not train_pixel_coords:
            raise ValueError(
                "CHK-SPEC-PCA-LEAK-001: train_pixel_coords must be provided when fit_domain='train_split_only'."
            )
        for x, y in train_pixel_coords:
            if isinstance(x, bool) or isinstance(y, bool) or int(x) != x or int(y) != y or not (0 <= x < width and 0 <= y < height):
                raise ValueError("PCA fit coordinates must be integer pixels inside the raster")
            fit_vectors.append([float(cube[b][y][x]) for b in range(bands)])
        if len(set(train_pixel_coords)) != len(train_pixel_coords):
            raise ValueError("PCA fit coordinates must not contain duplicates")
    else:
        for y in range(height):
            for x in range(width):
                fit_vectors.append([float(cube[b][y][x]) for b in range(bands)])

    n_samples = len(fit_vectors)
    if n_samples < 2:
        raise ValueError("PCA requires at least 2 sample pixels to estimate covariance.")

    means = [sum(vec[b] for vec in fit_vectors) / n_samples for b in range(bands)]
    cov = [[0.0 for _ in range(bands)] for _ in range(bands)]
    for vec in fit_vectors:
        centered = [vec[b] - means[b] for b in range(bands)]
        for i in range(bands):
            for j in range(i, bands):
                cov[i][j] += centered[i] * centered[j]
    for i in range(bands):
        for j in range(i, bands):
            cov[i][j] /= float(n_samples - 1)
            cov[j][i] = cov[i][j]

    eigenvalues, eigenvectors = _jacobi_eigen_symmetric(cov)
    total_var = sum(eigenvalues) or 1.0
    explained_ratio = [val / total_var for val in eigenvalues]

    k = n_components if n_components is not None else bands
    k = max(1, min(k, bands))

    components_cube: list[list[list[float]]] = []
    for comp_idx in range(k):
        vec = eigenvectors[comp_idx]
        comp_band: list[list[float]] = []
        for y in range(height):
            row_out: list[float] = []
            for x in range(width):
                score = sum((float(cube[b][y][x]) - means[b]) * vec[b] for b in range(bands))
                row_out.append(round(score, 6))
            comp_band.append(row_out)
        components_cube.append(comp_band)

    return {
        "components_cube": components_cube,
        "fit_domain": fit_domain,
        "fitted_sample_count": n_samples,
        "means": [round(m, 6) for m in means],
        "eigenvalues": [round(v, 6) for v in eigenvalues[:k]],
        "explained_variance_ratio": [round(r, 6) for r in explained_ratio[:k]],
        "eigenvectors": [[round(x, 6) for x in vec] for vec in eigenvectors[:k]],
    }


def compute_tasseled_cap_tm(
    cube: Sequence[Sequence[Sequence[float | int]]],
    third_component_label: str = "Third (Wetness-related)",
) -> dict[str, Any]:
    """Compute Landsat 5 TM 6-band K-T transform; enforces 'Third' boundary naming."""
    bands, height, width = validate_cube_shape(cube)
    if bands != 6:
        raise ValueError(f"Landsat 5 TM K-T transform expects 6 reflective bands (TM1..5,7), got {bands}.")
    if "Third" not in third_component_label:
        raise ValueError(
            "CHK-SPEC-KT-THIRD-001: Landsat 5 TM 3rd Tasseled Cap component must retain 'Third' "
            "in its label rather than claiming calibrated absolute Wetness."
        )

    component_specs = [
        ("Brightness", LANDSAT5_TM_KT_COEFFICIENTS["Brightness"]),
        ("Greenness", LANDSAT5_TM_KT_COEFFICIENTS["Greenness"]),
        (third_component_label, LANDSAT5_TM_KT_COEFFICIENTS["Third (Wetness-related)"]),
    ]
    out_components: dict[str, list[list[float]]] = {}
    for name, weights in component_specs:
        layer: list[list[float]] = []
        for y in range(height):
            row: list[float] = []
            for x in range(width):
                val = sum(float(cube[b][y][x]) * weights[b] for b in range(6))
                row.append(round(val, 6))
            layer.append(row)
        out_components[name] = layer

    return {
        "components": out_components,
        "component_names": [name for name, _ in component_specs],
        "coefficients": {name: list(weights) for name, weights in component_specs},
        "dtype": "float64",
    }
