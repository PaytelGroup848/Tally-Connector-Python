"""
CtrlBooks - Safe Mapping Transformation Preview Engine
------------------------------------------------------------------
Transforms sample source records through configured mapping rules to generate target object previews.
Enforces strict read-only execution with zero database or target API mutations.
"""

from typing import Dict, Any, List, Optional
from shared.db.models.mapping import MappingDefinition, MappingFieldRule
from shared.mapping.transformation_engine import transformation_engine, TransformationError

class MappingPreviewEngine:
    @classmethod
    def generate_preview(
        cls,
        mapping: MappingDefinition,
        source_record: Dict[str, Any],
        field_rules: Optional[List[MappingFieldRule]] = None
    ) -> Dict[str, Any]:
        rules = field_rules if field_rules is not None else (mapping.field_rules or [])
        active_rules = sorted([r for r in rules if r.is_active], key=lambda x: getattr(x, "sort_order", 0) or 0)

        target_preview: Dict[str, Any] = {}
        applied_transformations: List[Dict[str, Any]] = []

        for rule in active_rules:
            s_val = source_record.get(rule.source_field)
            if s_val is None:
                for k, v in source_record.items():
                    if str(k).strip().lower() == str(rule.source_field).strip().lower():
                        s_val = v
                        break

            try:
                transformed_val = transformation_engine.apply_transformation(
                    source_value=s_val,
                    transformation_type=rule.transformation_type,
                    transformation_config_json=rule.transformation_config_json,
                    default_value=rule.default_value,
                    record_context=source_record
                )
                target_preview[rule.target_field] = transformed_val
                applied_transformations.append({
                    "source_field": rule.source_field,
                    "target_field": rule.target_field,
                    "transformation": rule.transformation_type,
                    "source_value": s_val,
                    "target_value": transformed_val,
                    "status": "SUCCESS"
                })
            except TransformationError as err:
                target_preview[rule.target_field] = f"[ERROR: {str(err)}]"
                applied_transformations.append({
                    "source_field": rule.source_field,
                    "target_field": rule.target_field,
                    "transformation": rule.transformation_type,
                    "source_value": s_val,
                    "error": str(err),
                    "status": "FAILED"
                })

        return {
            "mapping_id": mapping.id,
            "mapping_name": mapping.name,
            "canonical_entity_type": mapping.canonical_entity_type,
            "source_connector_id": mapping.source_connector_id,
            "target_connector_id": mapping.target_connector_id,
            "is_preview": True,
            "notice": "PREVIEW ONLY — No target records created or updated.",
            "source_record": source_record,
            "target_preview": target_preview,
            "applied_transformations": applied_transformations
        }

mapping_preview_engine = MappingPreviewEngine()
