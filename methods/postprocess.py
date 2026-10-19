"""Post-processing method package: Majority, Clump, Sieve, and water-loss branch comparator (T21)."""
from __future__ import annotations

from collections import Counter, deque
from typing import Any, Mapping, Sequence

from methods.preprocess import validate_cube_shape

VALID_IMPLEMENTATION_KINDS = (
    "native_envi_postprocess",
    "approximate_postprocess",
)


def _validate_2d_map(class_map: Sequence[Sequence[int]]) -> tuple[int, int]:
    _, height, width = validate_cube_shape([class_map])
    return height, width


def count_class_pixels(class_map: Sequence[Sequence[int]]) -> dict[int, int]:
    height, width = _validate_2d_map(class_map)
    counts: Counter[int] = Counter()
    for y in range(height):
        for x in range(width):
            counts[int(class_map[y][x])] += 1
    return dict(sorted(counts.items()))


def majority_filter(
    class_map: Sequence[Sequence[int]],
    window_size: int = 3,
    exclude_unclassified: bool = True,
) -> list[list[int]]:
    """Sliding-window majority (mode) filter on a 2D integer classification map."""
    height, width = _validate_2d_map(class_map)
    if window_size < 1 or window_size % 2 == 0:
        raise ValueError("window_size must be a positive odd integer")
    radius = window_size // 2
    out_map: list[list[int]] = []

    for y in range(height):
        row_out: list[int] = []
        for x in range(width):
            center_val = int(class_map[y][x])
            neighbors: list[int] = []
            for dy in range(-radius, radius + 1):
                ny = y + dy
                if 0 <= ny < height:
                    for dx in range(-radius, radius + 1):
                        nx = x + dx
                        if 0 <= nx < width:
                            val = int(class_map[ny][nx])
                            if exclude_unclassified and val == 0:
                                continue
                            neighbors.append(val)
            if not neighbors:
                row_out.append(center_val)
            else:
                freq = Counter(neighbors)
                max_cnt = max(freq.values())
                # Keep center_val on tie if it achieves max_cnt
                if freq.get(center_val, 0) == max_cnt:
                    row_out.append(center_val)
                else:
                    best_code = min(code for code, cnt in freq.items() if cnt == max_cnt)
                    row_out.append(best_code)
        out_map.append(row_out)
    return out_map


def clump_classes(
    class_map: Sequence[Sequence[int]],
    kernel_size: int = 3,
    class_order: Sequence[int] | None = None,
) -> list[list[int]]:
    """Morphological closing (dilation followed by erosion) per class to clump adjacent patches."""
    height, width = _validate_2d_map(class_map)
    if kernel_size < 1 or kernel_size % 2 == 0:
        raise ValueError("kernel_size must be a positive odd integer")
    radius = kernel_size // 2

    if class_order is None:
        present = sorted(set(int(v) for row in class_map for v in row if int(v) != 0))
    else:
        present = [int(c) for c in class_order if int(c) != 0]

    result = [[int(class_map[y][x]) for x in range(width)] for y in range(height)]

    for code in present:
        mask = [[1 if result[y][x] == code else 0 for x in range(width)] for y in range(height)]
        # Dilation
        dilated = [[0 for _ in range(width)] for _ in range(height)]
        for y in range(height):
            for x in range(width):
                found = False
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if 0 <= ny < height:
                        for dx in range(-radius, radius + 1):
                            nx = x + dx
                            if 0 <= nx < width and mask[ny][nx] == 1:
                                found = True
                                break
                    if found:
                        break
                if found:
                    dilated[y][x] = 1
        # Erosion
        closed = [[0 for _ in range(width)] for _ in range(height)]
        for y in range(height):
            for x in range(width):
                all_one = True
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if 0 <= ny < height:
                        for dx in range(-radius, radius + 1):
                            nx = x + dx
                            if 0 <= nx < width and dilated[ny][nx] == 0:
                                all_one = False
                                break
                    if not all_one:
                        break
                if all_one:
                    closed[y][x] = 1
        for y in range(height):
            for x in range(width):
                if closed[y][x] == 1:
                    result[y][x] = code
    return result


def sieve_classes(
    class_map: Sequence[Sequence[int]],
    min_blob_size: int = 2,
    connectivity: int = 8,
    unclassified_code: int = 0,
) -> list[list[int]]:
    """Connected-component Sieve: blobs smaller than min_blob_size are reassigned to 0=Unclassified."""
    height, width = _validate_2d_map(class_map)
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    if min_blob_size < 1:
        raise ValueError("min_blob_size must be >= 1")

    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        offsets.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])

    visited = [[False for _ in range(width)] for _ in range(height)]
    out_map = [[int(class_map[y][x]) for x in range(width)] for y in range(height)]

    for y in range(height):
        for x in range(width):
            if visited[y][x]:
                continue
            code = out_map[y][x]
            visited[y][x] = True
            if code == unclassified_code:
                continue
            queue: deque[tuple[int, int]] = deque([(y, x)])
            component: list[tuple[int, int]] = [(y, x)]
            while queue:
                cy, cx = queue.popleft()
                for dy, dx in offsets:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and not visited[ny][nx]:
                        if out_map[ny][nx] == code:
                            visited[ny][nx] = True
                            queue.append((ny, nx))
                            component.append((ny, nx))
            if len(component) < min_blob_size:
                for cy, cx in component:
                    out_map[cy][cx] = unclassified_code

    return out_map


def evaluate_postprocess_branches(
    raw_map: Sequence[Sequence[int]],
    branch_maps: Mapping[str, Sequence[Sequence[int]]],
    class_schema: Mapping[int, Mapping[str, str]],
    water_semantic_id: str = "water",
    water_loss_threshold_pct: float = 15.0,
    implementation_kind: str = "approximate_postprocess",
) -> dict[str, Any]:
    """Compare post-processing branches, enforce native vs approximate label, and flag water loss."""
    if implementation_kind not in VALID_IMPLEMENTATION_KINDS:
        raise ValueError(
            f"CHK-POST-MODE-001: implementation_kind={implementation_kind!r} must be one of "
            f"{VALID_IMPLEMENTATION_KINDS}."
        )

    raw_counts = count_class_pixels(raw_map)
    water_codes = [
        int(code)
        for code, info in class_schema.items()
        if info.get("semantic_id") == water_semantic_id
    ]
    water_code = water_codes[0] if water_codes else None
    raw_water_pixels = raw_counts.get(water_code, 0) if water_code is not None else 0

    branch_summaries: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []

    for branch_id, b_map in branch_maps.items():
        b_counts = count_class_pixels(b_map)
        semantic_counts: dict[str, int] = {}
        semantic_deltas: dict[str, int] = {}
        for code, info in sorted(class_schema.items()):
            c_int = int(code)
            sem_id = info["semantic_id"]
            cnt = b_counts.get(c_int, 0)
            r_cnt = raw_counts.get(c_int, 0)
            semantic_counts[sem_id] = cnt
            semantic_deltas[sem_id] = cnt - r_cnt

        water_loss_pct = 0.0
        water_loss_warning = False
        if water_code is not None and raw_water_pixels > 0:
            b_water = b_counts.get(water_code, 0)
            loss = max(0, raw_water_pixels - b_water)
            water_loss_pct = round(loss * 100.0 / float(raw_water_pixels), 2)
            if water_loss_pct >= water_loss_threshold_pct:
                water_loss_warning = True
                warnings.append(
                    {
                        "check_id": "CHK-POST-WATER-LOSS-001",
                        "branch_id": branch_id,
                        "water_loss_pct": water_loss_pct,
                        "raw_water_pixels": raw_water_pixels,
                        "branch_water_pixels": b_water,
                        "message": (
                            f"Branch {branch_id!r} eroded {water_loss_pct}% of {water_semantic_id!r} "
                            f"pixels ({raw_water_pixels} -> {b_water}), exceeding threshold "
                            f"{water_loss_threshold_pct}%."
                        ),
                    }
                )

        branch_summaries[branch_id] = {
            "branch_id": branch_id,
            "implementation_kind": implementation_kind,
            "native_code_counts": b_counts,
            "semantic_counts": semantic_counts,
            "semantic_deltas_from_raw": semantic_deltas,
            "water_loss_pct": water_loss_pct,
            "water_loss_warning": water_loss_warning,
        }

    return {
        "implementation_kind": implementation_kind,
        "raw_native_code_counts": raw_counts,
        "branches": branch_summaries,
        "water_loss_warnings": warnings,
    }
