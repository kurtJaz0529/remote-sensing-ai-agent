"""Foundational 8-stage remote sensing skills package (T12)."""
from skills.loader import (
    FOUNDATIONAL_SKILL_IDS,
    SkillRegistry,
    load_skill_schema,
    load_skills_catalog,
    validate_skill,
)

__all__ = [
    "FOUNDATIONAL_SKILL_IDS",
    "SkillRegistry",
    "load_skill_schema",
    "load_skills_catalog",
    "validate_skill",
]
