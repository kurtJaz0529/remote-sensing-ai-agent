"""Classification method package: Parallelepiped, Maximum Likelihood, K-Means, and ISODATA (T20)."""
from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence

from methods.preprocess import validate_cube_shape

VALID_OVERLAP_POLICIES = (
    "first_class",
    "min_standardized_distance",
    "unclassified_on_overlap",
)


def _mean_and_std(samples: Sequence[Sequence[float | int]], bands: int) -> tuple[list[float], list[float]]:
    n = len(samples)
    if n == 0:
        raise ValueError("Cannot compute class statistics from empty sample list")
    means = [sum(float(s[b]) for s in samples) / n for b in range(bands)]
    if n == 1:
        stds = [1.0 for _ in range(bands)]
    else:
        stds = [
            max(
                1e-6,
                math.sqrt(sum((float(s[b]) - means[b]) ** 2 for s in samples) / float(n - 1)),
            )
            for b in range(bands)
        ]
    return means, stds


def parallelepiped_classify(
    cube: Sequence[Sequence[Sequence[float | int]]],
    training_samples_by_class: Mapping[int, Sequence[Sequence[float | int]]],
    std_multiplier: float = 2.0,
    overlap_policy: str = "min_standardized_distance",
) -> dict[str, Any]:
    """Parallelepiped classifier with explicit multi-class overlap disambiguation (CHK-CLASS-PP-001)."""
    bands, height, width = validate_cube_shape(cube)
    if overlap_policy not in VALID_OVERLAP_POLICIES:
        raise ValueError(
            f"CHK-CLASS-PP-001: overlap_policy={overlap_policy!r} is invalid; "
            f"must be one of {VALID_OVERLAP_POLICIES}."
        )
    if std_multiplier <= 0:
        raise ValueError("std_multiplier must be positive")

    class_stats: dict[int, dict[str, list[float]]] = {}
    ordered_codes = [int(c) for c in training_samples_by_class.keys() if int(c) != 0]
    for code in ordered_codes:
        means, stds = _mean_and_std(training_samples_by_class[code], bands)
        lows = [means[b] - std_multiplier * stds[b] for b in range(bands)]
        highs = [means[b] + std_multiplier * stds[b] for b in range(bands)]
        class_stats[code] = {"means": means, "stds": stds, "lows": lows, "highs": highs}

    class_map: list[list[int]] = []
    overlap_count = 0
    unclassified_count = 0
    total_pixels = height * width

    for y in range(height):
        row_out: list[int] = []
        for x in range(width):
            pix = [float(cube[b][y][x]) for b in range(bands)]
            matched_codes: list[int] = []
            for code in ordered_codes:
                st = class_stats[code]
                if all(st["lows"][b] <= pix[b] <= st["highs"][b] for b in range(bands)):
                    matched_codes.append(code)

            if not matched_codes:
                row_out.append(0)
                unclassified_count += 1
            elif len(matched_codes) == 1:
                row_out.append(matched_codes[0])
            else:
                overlap_count += 1
                if overlap_policy == "first_class":
                    row_out.append(matched_codes[0])
                elif overlap_policy == "unclassified_on_overlap":
                    row_out.append(0)
                    unclassified_count += 1
                else:
                    best_code = min(
                        matched_codes,
                        key=lambda c: sum(
                            ((pix[b] - class_stats[c]["means"][b]) / class_stats[c]["stds"][b]) ** 2
                            for b in range(bands)
                        ),
                    )
                    row_out.append(best_code)
        class_map.append(row_out)

    return {
        "class_map": class_map,
        "overlap_policy": overlap_policy,
        "std_multiplier": float(std_multiplier),
        "overlap_count": overlap_count,
        "overlap_ratio": round(overlap_count / float(total_pixels), 6),
        "unclassified_count": unclassified_count,
        "unclassified_ratio": round(unclassified_count / float(total_pixels), 6),
    }


def _invert_matrix_with_logdet(matrix: list[list[float]]) -> tuple[list[list[float]], float]:
    """Gauss-Jordan matrix inversion with partial pivoting and log-determinant in pure Python."""
    n = len(matrix)
    aug = [
        [float(matrix[i][j]) for j in range(n)] + [1.0 if i == j else 0.0 for j in range(n)]
        for i in range(n)
    ]
    log_det = 0.0
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        pivot_val = aug[pivot_row][col]
        if abs(pivot_val) <= 1e-14:
            raise ValueError("Singular covariance matrix")
        if pivot_row != col:
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        log_det += math.log(abs(pivot_val))
        for j in range(2 * n):
            aug[col][j] /= pivot_val
        for r in range(n):
            if r != col:
                factor = aug[r][col]
                if factor != 0.0:
                    for j in range(2 * n):
                        aug[r][j] -= factor * aug[col][j]
    inv = [row[n : 2 * n] for row in aug]
    return inv, log_det


def maximum_likelihood_classify(
    cube: Sequence[Sequence[Sequence[float | int]]],
    training_samples_by_class: Mapping[int, Sequence[Sequence[float | int]]],
    ridge_epsilon: float = 1e-3,
    allow_ridge_regularization: bool = True,
    max_mahalanobis_sq: float | None = None,
) -> dict[str, Any]:
    """Gaussian Maximum Likelihood classifier with covariance conditioning check (CHK-CLASS-MLC-001)."""
    bands, height, width = validate_cube_shape(cube)
    ordered_codes = sorted(int(c) for c in training_samples_by_class.keys() if int(c) != 0)
    if not ordered_codes:
        raise ValueError("training_samples_by_class must contain at least one positive class code")

    models: dict[int, dict[str, Any]] = {}
    regularized_classes: list[int] = []

    for code in ordered_codes:
        samples = training_samples_by_class[code]
        n = len(samples)
        if n < 2:
            raise ValueError(f"CHK-CLASS-MLC-001: Class {code} has fewer than 2 training samples")
        means = [sum(float(s[b]) for s in samples) / n for b in range(bands)]
        cov = [[0.0 for _ in range(bands)] for _ in range(bands)]
        for s in samples:
            diff = [float(s[b]) - means[b] for b in range(bands)]
            for i in range(bands):
                for j in range(i, bands):
                    cov[i][j] += diff[i] * diff[j]
        for i in range(bands):
            for j in range(i, bands):
                cov[i][j] /= float(n - 1)
                cov[j][i] = cov[i][j]

        try:
            if n <= bands:
                raise ValueError("Sample count <= band count causes rank-deficient covariance")
            inv_cov, log_det = _invert_matrix_with_logdet(cov)
        except ValueError:
            if not allow_ridge_regularization or ridge_epsilon <= 0:
                raise ValueError(
                    f"CHK-CLASS-MLC-001: Class {code} covariance is singular/rank-deficient and "
                    f"ridge regularization is disabled."
                )
            regularized_classes.append(code)
            reg_cov = [
                [cov[i][j] + (ridge_epsilon if i == j else 0.0) for j in range(bands)]
                for i in range(bands)
            ]
            inv_cov, log_det = _invert_matrix_with_logdet(reg_cov)

        models[code] = {"means": means, "inv_cov": inv_cov, "log_det": log_det}

    class_map: list[list[int]] = []
    unclassified_count = 0
    total_pixels = height * width

    for y in range(height):
        row_out: list[int] = []
        for x in range(width):
            pix = [float(cube[b][y][x]) for b in range(bands)]
            best_code = 0
            best_score = -math.inf
            best_maha = math.inf
            for code in ordered_codes:
                m = models[code]
                diff = [pix[b] - m["means"][b] for b in range(bands)]
                inv = m["inv_cov"]
                maha_sq = sum(
                    diff[i] * sum(inv[i][j] * diff[j] for j in range(bands)) for i in range(bands)
                )
                score = -0.5 * (m["log_det"] + maha_sq)
                if score > best_score:
                    best_score = score
                    best_code = code
                    best_maha = maha_sq
            if max_mahalanobis_sq is not None and best_maha > max_mahalanobis_sq:
                row_out.append(0)
                unclassified_count += 1
            else:
                row_out.append(best_code)
        class_map.append(row_out)

    return {
        "class_map": class_map,
        "regularized_classes": regularized_classes,
        "ridge_epsilon": float(ridge_epsilon),
        "unclassified_count": unclassified_count,
        "unclassified_ratio": round(unclassified_count / float(total_pixels), 6),
    }


def kmeans_classify(
    cube: Sequence[Sequence[Sequence[float | int]]],
    k: int = 6,
    max_iter: int = 30,
    tol: float = 1e-4,
    seed: int = 42,
) -> dict[str, Any]:
    """Deterministic K-Means clustering with quantile/seeded initialization (CHK-CLASS-KMEANS-001)."""
    bands, height, width = validate_cube_shape(cube)
    if k < 2:
        raise ValueError("k must be >= 2")

    pixels: list[list[float]] = []
    for y in range(height):
        for x in range(width):
            pixels.append([float(cube[b][y][x]) for b in range(bands)])

    n_pix = len(pixels)
    rng = random.Random(seed)
    # Deterministic quantile + seeded selection along band 0 brightness
    sorted_indices = sorted(range(n_pix), key=lambda idx: sum(pixels[idx]))
    centroids: list[list[float]] = []
    for c_idx in range(k):
        pos = int((c_idx + 0.5) * n_pix / k)
        pos = max(0, min(n_pix - 1, pos))
        centroids.append(list(pixels[sorted_indices[pos]]))

    labels = [1 for _ in range(n_pix)]
    iterations_run = 0
    for it in range(1, max_iter + 1):
        iterations_run = it
        clusters: list[list[int]] = [[] for _ in range(k)]
        for p_idx, vec in enumerate(pixels):
            best_c = min(
                range(k),
                key=lambda c: sum((vec[b] - centroids[c][b]) ** 2 for b in range(bands)),
            )
            labels[p_idx] = best_c + 1
            clusters[best_c].append(p_idx)

        max_shift = 0.0
        for c in range(k):
            if not clusters[c]:
                # Re-seed empty cluster deterministically
                pick = pixels[rng.randrange(n_pix)]
                new_cent = list(pick)
            else:
                cnt = float(len(clusters[c]))
                new_cent = [
                    sum(pixels[p_idx][b] for p_idx in clusters[c]) / cnt for b in range(bands)
                ]
            shift = math.sqrt(sum((new_cent[b] - centroids[c][b]) ** 2 for b in range(bands)))
            if shift > max_shift:
                max_shift = shift
            centroids[c] = new_cent
        if max_shift <= tol:
            break

    class_map: list[list[int]] = []
    idx = 0
    for y in range(height):
        row_out: list[int] = []
        for x in range(width):
            row_out.append(labels[idx])
            idx += 1
        class_map.append(row_out)

    return {
        "class_map": class_map,
        "cluster_count": k,
        "iterations_run": iterations_run,
        "centroids": [[round(v, 4) for v in cent] for cent in centroids],
    }


def isodata_classify(
    cube: Sequence[Sequence[Sequence[float | int]]],
    k_init: int = 6,
    k_min: int = 3,
    k_max: int = 10,
    max_iter: int = 20,
    min_samples_per_cluster: int = 5,
    split_std_threshold: float = 12.0,
    merge_distance_threshold: float = 5.0,
    seed: int = 42,
) -> dict[str, Any]:
    """ISODATA clustering tracking split/merge events and K-Means degeneracy (CHK-CLASS-ISO-001)."""
    bands, height, width = validate_cube_shape(cube)
    pixels: list[list[float]] = []
    for y in range(height):
        for x in range(width):
            pixels.append([float(cube[b][y][x]) for b in range(bands)])
    n_pix = len(pixels)
    sorted_indices = sorted(range(n_pix), key=lambda idx: sum(pixels[idx]))

    centroids: list[list[float]] = []
    for c_idx in range(k_init):
        pos = max(0, min(n_pix - 1, int((c_idx + 0.5) * n_pix / k_init)))
        centroids.append(list(pixels[sorted_indices[pos]]))

    split_events = 0
    merge_events = 0
    labels = [1 for _ in range(n_pix)]

    for it in range(1, max_iter + 1):
        k_curr = len(centroids)
        clusters: list[list[int]] = [[] for _ in range(k_curr)]
        for p_idx, vec in enumerate(pixels):
            best_c = min(
                range(k_curr),
                key=lambda c: sum((vec[b] - centroids[c][b]) ** 2 for b in range(bands)),
            )
            labels[p_idx] = best_c + 1
            clusters[best_c].append(p_idx)

        # 1. Remove tiny clusters if above k_min
        new_centroids: list[list[float]] = []
        valid_clusters: list[list[int]] = []
        for c_idx, members in enumerate(clusters):
            if len(members) < min_samples_per_cluster and len(new_centroids) + (k_curr - c_idx) > k_min:
                continue
            if members:
                cnt = float(len(members))
                new_centroids.append(
                    [sum(pixels[p][b] for p in members) / cnt for b in range(bands)]
                )
                valid_clusters.append(members)
        if not new_centroids:
            new_centroids = list(centroids)
            valid_clusters = list(clusters)

        centroids = new_centroids
        clusters = valid_clusters

        if it == max_iter:
            break

        # 2. Split step on odd iterations (or when k_curr <= k_min)
        if (it % 2 == 1 or len(centroids) <= k_min) and len(centroids) < k_max:
            post_split_centroids: list[list[float]] = []
            for c_idx, members in enumerate(clusters):
                cent = centroids[c_idx]
                if len(members) >= 2 * min_samples_per_cluster and len(post_split_centroids) + (len(centroids) - c_idx) < k_max:
                    stds = [
                        math.sqrt(
                            sum((pixels[p][b] - cent[b]) ** 2 for p in members) / float(len(members))
                        )
                        for b in range(bands)
                    ]
                    max_b = max(range(bands), key=lambda b: stds[b])
                    if stds[max_b] > split_std_threshold:
                        c_plus = list(cent)
                        c_minus = list(cent)
                        c_plus[max_b] += 0.5 * stds[max_b]
                        c_minus[max_b] -= 0.5 * stds[max_b]
                        post_split_centroids.append(c_minus)
                        post_split_centroids.append(c_plus)
                        split_events += 1
                        continue
                post_split_centroids.append(cent)
            centroids = post_split_centroids

        # 3. Merge step on even iterations
        elif len(centroids) > k_min:
            merged_used: set[int] = set()
            post_merge_centroids: list[list[float]] = []
            for i in range(len(centroids)):
                if i in merged_used:
                    continue
                merged_partner = None
                for j in range(i + 1, len(centroids)):
                    if j in merged_used:
                        continue
                    dist = math.sqrt(
                        sum((centroids[i][b] - centroids[j][b]) ** 2 for b in range(bands))
                    )
                    if dist < merge_distance_threshold and (len(centroids) - len(merged_used) > k_min):
                        merged_partner = j
                        break
                if merged_partner is not None:
                    merged_used.add(i)
                    merged_used.add(merged_partner)
                    n_i = float(max(1, len(clusters[i])))
                    n_j = float(max(1, len(clusters[merged_partner])))
                    comb = [
                        (n_i * centroids[i][b] + n_j * centroids[merged_partner][b]) / (n_i + n_j)
                        for b in range(bands)
                    ]
                    post_merge_centroids.append(comb)
                    merge_events += 1
                else:
                    post_merge_centroids.append(centroids[i])
            centroids = post_merge_centroids

    # Final assignment pass
    k_final = len(centroids)
    for p_idx, vec in enumerate(pixels):
        best_c = min(
            range(k_final),
            key=lambda c: sum((vec[b] - centroids[c][b]) ** 2 for b in range(bands)),
        )
        labels[p_idx] = best_c + 1

    class_map: list[list[int]] = []
    idx = 0
    for y in range(height):
        row_out: list[int] = []
        for x in range(width):
            row_out.append(labels[idx])
            idx += 1
        class_map.append(row_out)

    degenerated_to_kmeans = split_events == 0 and merge_events == 0
    return {
        "class_map": class_map,
        "initial_cluster_count": k_init,
        "final_cluster_count": k_final,
        "split_events": split_events,
        "merge_events": merge_events,
        "degenerated_to_kmeans": degenerated_to_kmeans,
        "centroids": [[round(v, 4) for v in cent] for cent in centroids],
    }
