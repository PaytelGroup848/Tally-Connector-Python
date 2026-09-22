"""
CtrlBooks - Data Mapping & Field Mapping Service
------------------------------------------------------------
Core application service for managing mapping definitions, field transformation rules,
versioning, validation, field matching suggestions, preview, activation, and audit logging.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from shared.repositories.mapping_repo import MappingRepository
from shared.repositories.connector_repo import ConnectorRepository
from shared.repositories.system_repo import ActivityLogRepository
from shared.mapping.canonical_registry import canonical_registry
from shared.mapping.suggestion_engine import field_suggestion_engine
from shared.mapping.validation_service import mapping_validation_service
from shared.mapping.preview_service import mapping_preview_engine
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.services.mapping")

class MappingService:
    def __init__(self):
        self.mapping_repo = MappingRepository()
        self.connector_repo = ConnectorRepository()
        self.audit_repo = ActivityLogRepository()

    def create_mapping(
        self,
        db: Session,
        payload: Dict[str, Any],
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Creates a new mapping definition and initializes version 1."""
        name = (payload.get("name") or "").strip()
        source_connector_id = payload.get("source_connector_id")
        source_company_identifier = (payload.get("source_company_identifier") or "").strip()
        target_connector_id = payload.get("target_connector_id")
        target_company_identifier = (payload.get("target_company_identifier") or "").strip()
        canonical_entity_type = (payload.get("canonical_entity_type") or "").strip().upper()
        description = payload.get("description")

        if not name:
            raise ValidationError("Mapping name is required.")
        if not source_connector_id:
            raise ValidationError("Source connector ID is required.")
        if not source_company_identifier:
            raise ValidationError("Source company identifier is required.")
        if not target_connector_id:
            raise ValidationError("Target connector ID is required.")
        if not target_company_identifier:
            raise ValidationError("Target company identifier is required.")
        if not canonical_entity_type:
            raise ValidationError("Canonical entity type is required.")

        src_conn = self.connector_repo.get_by_id_or_raise(db, source_connector_id)
        if not src_conn.is_active:
            raise ValidationError(f"Source connector '{src_conn.name}' is inactive.")

        tgt_conn = self.connector_repo.get_by_id_or_raise(db, target_connector_id)
        if not tgt_conn.is_active:
            raise ValidationError(f"Target connector '{tgt_conn.name}' is inactive.")

        if not canonical_registry.is_entity_type_supported(canonical_entity_type):
            raise ValidationError(f"Unsupported canonical entity type '{canonical_entity_type}'. Allowed: {', '.join(canonical_registry.get_supported_entity_types())}")

        mapping = self.mapping_repo.create_mapping(
            db=db,
            name=name,
            source_connector_id=source_connector_id,
            source_company_identifier=source_company_identifier,
            target_connector_id=target_connector_id,
            target_company_identifier=target_company_identifier,
            canonical_entity_type=canonical_entity_type,
            description=description,
            status="DRAFT",
            created_by=acting_user_id
        )

        self.mapping_repo.create_version(
            db=db,
            mapping_id=mapping.id,
            version_number=1,
            change_summary="Initial draft mapping created",
            created_by=acting_user_id
        )

        self.audit_repo.log_activity(
            db=db,
            event_type="MAPPING_CREATED",
            status="SUCCESS",
            message=f"Created mapping definition '{mapping.name}' ({mapping.id}) for scope {canonical_entity_type}",
            user_id=acting_user_id,
            connector_id=source_connector_id,
            request_id=request_id
        )

        return self.get_mapping(db, mapping.id)

    def get_mapping(self, db: Session, mapping_id: str) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        field_rules = self.mapping_repo.list_field_rules(db, mapping_id)
        versions = self.mapping_repo.list_versions(db, mapping_id)

        result = self.mapping_repo._to_dict(mapping)
        result["field_rules"] = [
            {
                "id": r.id,
                "source_field": r.source_field,
                "target_field": r.target_field,
                "source_data_type": r.source_data_type,
                "target_data_type": r.target_data_type,
                "is_required": r.is_required,
                "default_value": r.default_value,
                "transformation_type": r.transformation_type,
                "transformation_config": json.loads(r.transformation_config_json) if r.transformation_config_json else {},
                "sort_order": r.sort_order,
                "is_active": r.is_active
            }
            for r in field_rules
        ]
        result["versions"] = [
            {
                "id": v.id,
                "version_number": v.version_number,
                "status": v.status,
                "change_summary": v.change_summary,
                "created_at": v.created_at.isoformat() if v.created_at else None
            }
            for v in versions
        ]
        return result

    def list_mappings(
        self,
        db: Session,
        source_connector_id: Optional[str] = None,
        target_connector_id: Optional[str] = None,
        canonical_entity_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        return self.mapping_repo.list_mappings(
            db=db,
            source_connector_id=source_connector_id,
            target_connector_id=target_connector_id,
            canonical_entity_type=canonical_entity_type,
            status=status,
            search=search,
            page=page,
            page_size=page_size
        )

    def update_mapping(
        self,
        db: Session,
        mapping_id: str,
        payload: Dict[str, Any],
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)

        if "name" in payload and payload["name"]:
            mapping.name = payload["name"].strip()
        if "description" in payload:
            mapping.description = payload["description"]

        if mapping.status == "ACTIVE":
            mapping.status = "DRAFT"
            mapping.current_version += 1
            self.mapping_repo.create_version(
                db=db,
                mapping_id=mapping.id,
                version_number=mapping.current_version,
                change_summary=payload.get("change_summary", "Updated mapping definition details"),
                created_by=acting_user_id
            )

        mapping.updated_by = acting_user_id
        db.commit()

        self.audit_repo.log_activity(
            db=db,
            event_type="MAPPING_UPDATED",
            status="SUCCESS",
            message=f"Updated mapping definition '{mapping.name}' ({mapping.id})",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return self.get_mapping(db, mapping.id)

    def archive_mapping(
        self,
        db: Session,
        mapping_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        mapping.status = "ARCHIVED"
        mapping.deleted_at = datetime.now(timezone.utc)
        mapping.updated_by = acting_user_id
        db.commit()

        self.audit_repo.log_activity(
            db=db,
            event_type="MAPPING_ARCHIVED",
            status="SUCCESS",
            message=f"Archived mapping definition '{mapping.name}' ({mapping.id})",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return {"id": mapping.id, "status": "ARCHIVED", "message": "Mapping definition archived successfully."}

    def add_field_rule(
        self,
        db: Session,
        mapping_id: str,
        payload: Dict[str, Any],
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)

        source_field = (payload.get("source_field") or "").strip()
        target_field = (payload.get("target_field") or "").strip()
        source_data_type = (payload.get("source_data_type") or "STRING").strip().upper()
        target_data_type = (payload.get("target_data_type") or "STRING").strip().upper()
        is_required = bool(payload.get("is_required", False))
        default_value = payload.get("default_value")
        transformation_type = (payload.get("transformation_type") or "NONE").strip().upper()
        transformation_config = payload.get("transformation_config") or {}
        sort_order = int(payload.get("sort_order", 0))

        if not source_field:
            raise ValidationError("Source field name is required.")
        if not target_field:
            raise ValidationError("Target field name is required.")

        config_json = json.dumps(transformation_config) if isinstance(transformation_config, dict) else transformation_config

        rule = self.mapping_repo.create_field_rule(
            db=db,
            mapping_id=mapping_id,
            source_field=source_field,
            target_field=target_field,
            source_data_type=source_data_type,
            target_data_type=target_data_type,
            is_required=is_required,
            default_value=default_value,
            transformation_type=transformation_type,
            transformation_config_json=config_json,
            sort_order=sort_order
        )

        self.audit_repo.log_activity(
            db=db,
            event_type="FIELD_MAPPING_CREATED",
            status="SUCCESS",
            message=f"Added field rule '{source_field} -> {target_field}' to mapping '{mapping.name}'",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return {
            "id": rule.id,
            "source_field": rule.source_field,
            "target_field": rule.target_field,
            "source_data_type": rule.source_data_type,
            "target_data_type": rule.target_data_type,
            "is_required": rule.is_required,
            "default_value": rule.default_value,
            "transformation_type": rule.transformation_type,
            "transformation_config": transformation_config,
            "sort_order": rule.sort_order,
            "is_active": rule.is_active
        }

    def update_field_rule(
        self,
        db: Session,
        mapping_id: str,
        field_rule_id: str,
        payload: Dict[str, Any],
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        rule = self.mapping_repo.get_field_rule_or_raise(db, field_rule_id)

        if "source_field" in payload:
            rule.source_field = payload["source_field"].strip()
        if "target_field" in payload:
            rule.target_field = payload["target_field"].strip()
        if "source_data_type" in payload:
            rule.source_data_type = payload["source_data_type"].strip().upper()
        if "target_data_type" in payload:
            rule.target_data_type = payload["target_data_type"].strip().upper()
        if "is_required" in payload:
            rule.is_required = bool(payload["is_required"])
        if "default_value" in payload:
            rule.default_value = payload["default_value"]
        if "transformation_type" in payload:
            rule.transformation_type = payload["transformation_type"].strip().upper()
        if "transformation_config" in payload:
            cfg = payload["transformation_config"]
            rule.transformation_config_json = json.dumps(cfg) if isinstance(cfg, dict) else cfg
        if "sort_order" in payload:
            rule.sort_order = int(payload["sort_order"])

        db.commit()

        self.audit_repo.log_activity(
            db=db,
            event_type="FIELD_MAPPING_UPDATED",
            status="SUCCESS",
            message=f"Updated field rule '{rule.source_field} -> {rule.target_field}' on mapping '{mapping.name}'",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return {
            "id": rule.id,
            "source_field": rule.source_field,
            "target_field": rule.target_field,
            "source_data_type": rule.source_data_type,
            "target_data_type": rule.target_data_type,
            "is_required": rule.is_required,
            "default_value": rule.default_value,
            "transformation_type": rule.transformation_type,
            "transformation_config": json.loads(rule.transformation_config_json) if rule.transformation_config_json else {},
            "sort_order": rule.sort_order,
            "is_active": rule.is_active
        }

    def delete_field_rule(
        self,
        db: Session,
        mapping_id: str,
        field_rule_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        rule = self.mapping_repo.get_field_rule_or_raise(db, field_rule_id)

        s_field = rule.source_field
        t_field = rule.target_field
        self.mapping_repo.delete_field_rule(db, field_rule_id)

        self.audit_repo.log_activity(
            db=db,
            event_type="FIELD_MAPPING_DELETED",
            status="SUCCESS",
            message=f"Deleted field rule '{s_field} -> {t_field}' from mapping '{mapping.name}'",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return {"id": field_rule_id, "message": "Field mapping rule deleted successfully."}

    def get_field_suggestions(self, db: Session, mapping_id: str) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        src_conn = self.connector_repo.get_by_id_or_raise(db, mapping.source_connector_id)
        tgt_conn = self.connector_repo.get_by_id_or_raise(db, mapping.target_connector_id)

        src_fields = canonical_registry.get_supported_source_fields(src_conn.connector_type, mapping.canonical_entity_type)
        tgt_fields = canonical_registry.get_supported_target_fields(tgt_conn.connector_type, mapping.canonical_entity_type)

        suggestions = field_suggestion_engine.suggest_field_mappings(
            canonical_entity_type=mapping.canonical_entity_type,
            source_fields=src_fields,
            target_fields=tgt_fields
        )

        return {
            "mapping_id": mapping.id,
            "canonical_entity_type": mapping.canonical_entity_type,
            "suggestions": suggestions,
            "total_suggestions": len(suggestions),
            "note": "Suggestions require explicit user review and acceptance prior to activation."
        }

    def validate_mapping(
        self,
        db: Session,
        mapping_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        res = mapping_validation_service.validate_mapping_definition(db, mapping)
        self.mapping_repo.log_validation(db, mapping_id, res)

        self.audit_repo.log_activity(
            db=db,
            event_type="MAPPING_VALIDATED",
            status="SUCCESS" if res["is_valid"] else "WARNING",
            message=f"Validated mapping '{mapping.name}' ({mapping.id}) — Status: {res['status']}",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return res

    def preview_mapping(
        self,
        db: Session,
        mapping_id: str,
        source_record: Dict[str, Any]
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        if not source_record or not isinstance(source_record, dict):
            raise ValidationError("A valid source_record dictionary is required for transformation preview.")

        return mapping_preview_engine.generate_preview(
            mapping=mapping,
            source_record=source_record
        )

    def activate_mapping(
        self,
        db: Session,
        mapping_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)

        val_res = mapping_validation_service.validate_mapping_definition(db, mapping)
        if not val_res["is_valid"]:
            err_msgs = [e["message"] for e in val_res["errors"]]
            raise ValidationError(f"Cannot activate mapping '{mapping.name}'. Validation failed: {'; '.join(err_msgs)}")

        active_scope_mapping = self.mapping_repo.find_active_mapping_by_scope(
            db=db,
            source_connector_id=mapping.source_connector_id,
            source_company_identifier=mapping.source_company_identifier,
            target_connector_id=mapping.target_connector_id,
            target_company_identifier=mapping.target_company_identifier,
            canonical_entity_type=mapping.canonical_entity_type,
            exclude_mapping_id=mapping.id
        )
        if active_scope_mapping:
            active_scope_mapping.status = "INACTIVE"

        mapping.status = "ACTIVE"
        mapping.updated_by = acting_user_id
        db.commit()

        self.audit_repo.log_activity(
            db=db,
            event_type="MAPPING_ACTIVATED",
            status="SUCCESS",
            message=f"Activated mapping definition '{mapping.name}' ({mapping.id})",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return self.get_mapping(db, mapping.id)

    def deactivate_mapping(
        self,
        db: Session,
        mapping_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        mapping = self.mapping_repo.get_by_id_or_raise(db, mapping_id)
        mapping.status = "INACTIVE"
        mapping.updated_by = acting_user_id
        db.commit()

        self.audit_repo.log_activity(
            db=db,
            event_type="MAPPING_DEACTIVATED",
            status="SUCCESS",
            message=f"Deactivated mapping definition '{mapping.name}' ({mapping.id})",
            user_id=acting_user_id,
            connector_id=mapping.source_connector_id,
            request_id=request_id
        )

        return self.get_mapping(db, mapping.id)

mapping_service = MappingService()
