"""
CtrlBooks - Mapping Validation Engine
------------------------------------------------
Comprehensive validation service checking connector status, company scope, entity support,
required target field mappings, data type compatibility, and transformation configurations.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from shared.db.models.connector import Connector
from shared.db.models.mapping import MappingDefinition, MappingFieldRule
from shared.mapping.canonical_registry import canonical_registry, FIELD_REQUIREMENT_REQUIRED
from shared.mapping.transformation_engine import transformation_engine, TransformationError

class MappingValidationService:
    @classmethod
    def validate_mapping_definition(
        cls,
        db: Session,
        mapping: MappingDefinition,
        field_rules: Optional[List[MappingFieldRule]] = None
    ) -> Dict[str, Any]:
        errors: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []

        src_conn = db.get(Connector, mapping.source_connector_id)
        if not src_conn:
            errors.append({"field": "source_connector_id", "message": f"Source connector '{mapping.source_connector_id}' not found."})
        elif not src_conn.is_active:
            errors.append({"field": "source_connector_id", "message": f"Source connector '{src_conn.name}' is inactive."})

        tgt_conn = db.get(Connector, mapping.target_connector_id)
        if not tgt_conn:
            errors.append({"field": "target_connector_id", "message": f"Target connector '{mapping.target_connector_id}' not found."})
        elif not tgt_conn.is_active:
            errors.append({"field": "target_connector_id", "message": f"Target connector '{tgt_conn.name}' is inactive."})

        if not mapping.source_company_identifier:
            errors.append({"field": "source_company_identifier", "message": "Source company identifier is required."})
        if not mapping.target_company_identifier:
            errors.append({"field": "target_company_identifier", "message": "Target company identifier is required."})

        if not canonical_registry.is_entity_type_supported(mapping.canonical_entity_type):
            errors.append({"field": "canonical_entity_type", "message": f"Canonical entity type '{mapping.canonical_entity_type}' is not supported."})

        c_fields = {}
        if canonical_registry.is_entity_type_supported(mapping.canonical_entity_type):
            c_fields = canonical_registry.get_canonical_fields(mapping.canonical_entity_type)

        rules = field_rules if field_rules is not None else (mapping.field_rules or [])
        active_rules = [r for r in rules if r.is_active]

        mapped_target_fields = set()
        mapped_source_fields = set()

        for rule in active_rules:
            if rule.target_field in mapped_target_fields:
                errors.append({
                    "field": rule.target_field,
                    "message": f"Duplicate mapping rule for target field '{rule.target_field}'."
                })
            mapped_target_fields.add(rule.target_field)
            mapped_source_fields.add(rule.source_field)

            if c_fields and rule.target_field in c_fields:
                target_def = c_fields[rule.target_field]
                expected_tgt_type = target_def["data_type"]
                rule_tgt_type = (rule.target_data_type or "STRING").upper()
                rule_src_type = (rule.source_data_type or "STRING").upper()

                cls._validate_type_compatibility(
                    rule=rule,
                    rule_src_type=rule_src_type,
                    rule_tgt_type=rule_tgt_type,
                    expected_tgt_type=expected_tgt_type,
                    errors=errors,
                    warnings=warnings
                )

            try:
                transformation_engine.validate_transformation_type(rule.transformation_type)
                cfg = transformation_engine.parse_config(rule.transformation_config_json)
                if rule.transformation_type == "VALUE_MAP" and "mapping" not in cfg:
                    errors.append({
                        "field": rule.target_field,
                        "message": f"Transformation 'VALUE_MAP' on target field '{rule.target_field}' requires a 'mapping' dict in configuration."
                    })
                elif rule.transformation_type == "CONCAT" and "fields" not in cfg:
                    errors.append({
                        "field": rule.target_field,
                        "message": f"Transformation 'CONCAT' on target field '{rule.target_field}' requires a 'fields' list in configuration."
                    })
            except TransformationError as terr:
                errors.append({
                    "field": rule.target_field,
                    "message": f"Invalid transformation configuration on field '{rule.target_field}': {str(terr)}"
                })

        unmapped_required = []
        unmapped_optional = []

        if c_fields:
            for field_name, f_def in c_fields.items():
                req_level = f_def.get("requirement_level")
                if field_name not in mapped_target_fields:
                    if req_level == FIELD_REQUIREMENT_REQUIRED:
                        unmapped_required.append(field_name)
                        errors.append({
                            "field": field_name,
                            "message": f"Required target field '{field_name}' is not mapped."
                        })
                    else:
                        unmapped_optional.append(field_name)
                        warnings.append({
                            "field": field_name,
                            "message": f"Optional target field '{field_name}' is unmapped."
                        })

        if len(errors) > 0:
            status = "INVALID"
        elif len(warnings) > 0:
            status = "WARNING"
        else:
            status = "VALID"

        return {
            "status": status,
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "mapped_fields": list(mapped_target_fields),
            "unmapped_required_fields": unmapped_required,
            "unmapped_optional_fields": unmapped_optional
        }

    @staticmethod
    def _validate_type_compatibility(
        rule: MappingFieldRule,
        rule_src_type: str,
        rule_tgt_type: str,
        expected_tgt_type: str,
        errors: List[Dict[str, str]],
        warnings: List[Dict[str, str]]
    ):
        t_type = (rule.transformation_type or "NONE").upper()

        if rule_src_type == rule_tgt_type or (rule_src_type in ("NUMBER", "INTEGER") and rule_tgt_type in ("NUMBER", "INTEGER")):
            return

        if rule_src_type == "STRING" and rule_tgt_type in ("NUMBER", "INTEGER") and t_type != "STRING_TO_NUMBER":
            errors.append({
                "field": rule.target_field,
                "message": f"Type mismatch: Mapping source type '{rule_src_type}' to numeric target field '{rule.target_field}' requires 'STRING_TO_NUMBER' transformation."
            })
        elif rule_src_type in ("NUMBER", "INTEGER") and rule_tgt_type == "STRING" and t_type != "NUMBER_TO_STRING":
            warnings.append({
                "field": rule.target_field,
                "message": f"Type conversion: Source number field '{rule.source_field}' mapped to string target '{rule.target_field}'. Consider 'NUMBER_TO_STRING' transformation."
            })
        elif rule_src_type == "STRING" and rule_tgt_type == "DATE" and t_type != "STRING_TO_DATE":
            errors.append({
                "field": rule.target_field,
                "message": f"Type mismatch: Mapping string to date target field '{rule.target_field}' requires 'STRING_TO_DATE' transformation."
            })
        elif rule_src_type == "DATE" and rule_tgt_type == "STRING" and t_type != "DATE_TO_STRING":
            warnings.append({
                "field": rule.target_field,
                "message": f"Type conversion: Date source field mapped to string target '{rule.target_field}'. Consider 'DATE_TO_STRING' transformation."
            })
        elif rule_src_type != rule_tgt_type and t_type == "NONE":
            errors.append({
                "field": rule.target_field,
                "message": f"Incompatible data types: Source '{rule_src_type}' -> Target '{rule_tgt_type}' on field '{rule.target_field}' requires a transformation rule."
            })

mapping_validation_service = MappingValidationService()
