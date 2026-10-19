"""Client-neutral skill catalog loader, schema validator, and capability router (T12)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from retrieval.index import compatible

SKILLS_ROOT = Path(__file__).resolve().parent
SKILL_SCHEMA_PATH = SKILLS_ROOT / "skill_schema.json"
DEFAULT_CATALOG_PATH = SKILLS_ROOT / "catalog" / "skills_catalog.json"

FOUNDATIONAL_SKILL_IDS: tuple[str, ...] = (
    "task-intake",
    "dataset-audit",
    "raster-preprocess",
    "spectral-transform",
    "unsupervised-classification",
    "supervised-classification",
    "postprocess-and-evaluate",
    "deliver-and-learn",
)


def load_skill_schema() -> dict[str, Any]:
    return json.loads(SKILL_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_skill(skill_record: Mapping[str, Any]) -> dict[str, Any]:
    schema_obj = load_skill_schema()
    Draft202012Validator(schema_obj, format_checker=FormatChecker()).validate(dict(skill_record))
    return dict(skill_record)


def load_skills_catalog(catalog_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(catalog_path) if catalog_path else DEFAULT_CATALOG_PATH
    raw_list = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_list, list):
        raise ValueError("Skills catalog must be a JSON array of skill records")
    validated = [validate_skill(item) for item in raw_list]
    observed_ids = [item["skill_id"] for item in validated]
    if set(observed_ids) != set(FOUNDATIONAL_SKILL_IDS):
        missing = sorted(set(FOUNDATIONAL_SKILL_IDS) - set(observed_ids))
        raise ValueError(f"Skills catalog is missing foundational skills: {missing}")
    return sorted(validated, key=lambda item: int(item["stage_order"]))


class SkillRegistry:
    """Registry and capability router for the 8 foundational remote sensing skills."""

    def __init__(self, catalog_path: str | Path | None = None) -> None:
        self._skills = load_skills_catalog(catalog_path)
        self._by_id = {s["skill_id"]: s for s in self._skills}

    @property
    def skills(self) -> list[dict[str, Any]]:
        return list(self._skills)

    def get(self, skill_id: str) -> dict[str, Any]:
        if skill_id not in self._by_id:
            raise KeyError(f"Unknown skill_id: {skill_id!r}")
        return dict(self._by_id[skill_id])

    def route_backend(
        self,
        skill_id: str,
        preferred_software: str,
        environment_capabilities: Mapping[str, Mapping[str, Any]],
        allow_fallback: bool = True,
    ) -> dict[str, Any]:
        """Select a compatible software backend or fallback to PythonReference/alternative."""
        skill = self.get(skill_id)
        backends: Sequence[Mapping[str, Any]] = skill["supported_backends"]
        rejection_reasons: list[dict[str, str]] = []

        def _check_backend(backend: Mapping[str, Any]) -> tuple[bool, str]:
            sw = str(backend["software"])
            if sw == "PythonReference":
                py_cap = environment_capabilities.get(
                    "PythonReference", {"version": "3.13.7", "licenses": []}
                )
                ver = str(py_cap.get("version", "3.13.7"))
                if not compatible(str(backend["version_scope"]), ver):
                    return False, f"Python version {ver} outside scope {backend['version_scope']}"
                return True, "matched"

            if sw not in environment_capabilities:
                return False, f"Software {sw} not present in environment_capabilities"
            cap = environment_capabilities[sw]
            if not cap.get("available", True):
                return False, f"Software {sw} marked unavailable"
            ver = str(cap.get("version", ""))
            if not compatible(str(backend["version_scope"]), ver):
                return (
                    False,
                    f"Version {ver!r} does not satisfy scope {backend['version_scope']!r}",
                )
            avail_lic = set(str(x) for x in cap.get("licenses", []))
            req_lic = set(str(x) for x in backend.get("required_licenses", []))
            if not req_lic <= avail_lic:
                missing = sorted(req_lic - avail_lic)
                return False, f"Missing required licenses/toolboxes: {missing}"
            return True, "matched"

        # 1. Try preferred software first
        for b in backends:
            if b["software"] == preferred_software:
                ok, reason = _check_backend(b)
                if ok:
                    return {
                        "skill_id": skill_id,
                        "preferred_software": preferred_software,
                        "selected_software": b["software"],
                        "adapter_entrypoint": b["adapter_entrypoint"],
                        "verification_status": b["verification_status"],
                        "used_fallback": False,
                        "rejection_reasons": [],
                        "notes": b["notes"],
                    }
                rejection_reasons.append({"software": b["software"], "reason": reason})

        if not allow_fallback:
            raise ValueError(
                f"Preferred software {preferred_software!r} cannot execute {skill_id!r}: "
                f"{rejection_reasons}"
            )

        # 2. Try remaining backends in catalog order
        for b in backends:
            if b["software"] == preferred_software:
                continue
            ok, reason = _check_backend(b)
            if ok:
                return {
                    "skill_id": skill_id,
                    "preferred_software": preferred_software,
                    "selected_software": b["software"],
                    "adapter_entrypoint": b["adapter_entrypoint"],
                    "verification_status": b["verification_status"],
                    "used_fallback": True,
                    "fallback_policy": skill["fallback_policy"],
                    "rejection_reasons": rejection_reasons,
                    "notes": b["notes"],
                }
            rejection_reasons.append({"software": b["software"], "reason": reason})

        raise ValueError(
            f"No compatible backend found for skill {skill_id!r}; rejections={rejection_reasons}"
        )
