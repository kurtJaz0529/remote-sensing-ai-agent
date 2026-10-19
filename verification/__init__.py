"""Independent verification package: dataset audit, classification eval, and fault-injection checks (T07/T17/T22/T26/T29)."""
from verification.classification_eval import (
    audit_vector_raster_consistency,
    detect_pa_ua_swap,
    evaluate_classification,
    read_dbf_records,
    read_shp_header,
)
from verification.dataset_audit import (
    CANONICAL_CLASS_SCHEMAS,
    audit_class_mapping,
    audit_envi_dataset,
    audit_sample_split,
    parse_envi_header,
)
from verification.fault_scenarios import run_all_fault_scenarios

__all__ = [
    "CANONICAL_CLASS_SCHEMAS",
    "audit_class_mapping",
    "audit_envi_dataset",
    "audit_sample_split",
    "audit_vector_raster_consistency",
    "detect_pa_ua_swap",
    "evaluate_classification",
    "parse_envi_header",
    "read_dbf_records",
    "read_shp_header",
    "run_all_fault_scenarios",
]
