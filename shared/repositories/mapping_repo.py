"""
CtrlBooks - Mapping Definition Repository
------------------------------------------------------
Data access layer for mapping definitions, versions, field rules, and validation logs.
Supports paginated listings, scope uniqueness checks, and soft delete/archiving operations.
"""

import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from shared.db.models.mapping import MappingDefinition, MappingVersion, MappingFieldRule, MappingValidationLog
from shared.repositories.base import BaseRepository
from shared.exceptions import NotFoundException

class MappingRepository(BaseRepository[MappingDefinition]):
    def __init__(self):
        super().__init__(MappingDefinition)

    def create_mapping(
        self,
        db: Session,
        name: str,
        source_connector_id: str,
        source_company_identifier: str,
        target_connector_id: str,
        target_company_identifier: str,
        canonical_entity_type: str,
        description: Optional[str] = None,
        status: str = "DRAFT",
        created_by: Optional[str] = None
    ) -> MappingDefinition:
        mapping = MappingDefinition(
            name=name,
            source_connector_id=source_connector_id,
            source_company_identifier=source_company_identifier,
            target_connector_id=target_connector_id,
            target_company_identifier=target_company_identifier,
            canonical_entity_type=canonical_entity_type.upper(),
            description=description,
            status=status.upper(),
            current_version=1,
            created_by=created_by,
            updated_by=created_by
        )
        return self.create(db, mapping)

    def get_by_id_or_raise(self, db: Session, mapping_id: str) -> MappingDefinition:
        mapping = db.query(MappingDefinition).filter(
            MappingDefinition.id == mapping_id,
            MappingDefinition.deleted_at.is_(None)
        ).first()
        if not mapping:
            raise NotFoundException(f"Mapping definition '{mapping_id}' not found.")
        return mapping

    def find_active_mapping_by_scope(
        self,
        db: Session,
        source_connector_id: str,
        source_company_identifier: str,
        target_connector_id: str,
        target_company_identifier: str,
        canonical_entity_type: str,
        exclude_mapping_id: Optional[str] = None
    ) -> Optional[MappingDefinition]:
        q = db.query(MappingDefinition).filter(
            MappingDefinition.source_connector_id == source_connector_id,
            MappingDefinition.source_company_identifier == source_company_identifier,
            MappingDefinition.target_connector_id == target_connector_id,
            MappingDefinition.target_company_identifier == target_company_identifier,
            MappingDefinition.canonical_entity_type == canonical_entity_type.upper(),
            MappingDefinition.status == "ACTIVE",
            MappingDefinition.deleted_at.is_(None)
        )
        if exclude_mapping_id:
            q = q.filter(MappingDefinition.id != exclude_mapping_id)
        return q.first()

    def list_mappings(
        self,
        db: Session,
        source_connector_id: Optional[str] = None,
        target_connector_id: Optional[str] = None,
        canonical_entity_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        skip: Optional[int] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        if limit is not None and limit > 0:
            page_size = limit
        if skip is not None and skip >= 0:
            page = (skip // page_size) + 1
        q = db.query(MappingDefinition).filter(MappingDefinition.deleted_at.is_(None))

        if source_connector_id:
            q = q.filter(MappingDefinition.source_connector_id == source_connector_id)
        if target_connector_id:
            q = q.filter(MappingDefinition.target_connector_id == target_connector_id)
        if canonical_entity_type:
            q = q.filter(MappingDefinition.canonical_entity_type == canonical_entity_type.upper())
        if status:
            q = q.filter(MappingDefinition.status == status.upper())
        if search and search.strip():
            s = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    MappingDefinition.name.ilike(s),
                    MappingDefinition.description.ilike(s),
                    MappingDefinition.source_company_identifier.ilike(s),
                    MappingDefinition.target_company_identifier.ilike(s)
                )
            )

        total_count = q.count()
        offset = (page - 1) * page_size
        items = q.order_by(MappingDefinition.updated_at.desc()).offset(offset).limit(page_size).all()

        return {
            "items": [self._to_dict(i) for i in items],
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1
        }

    def create_version(
        self,
        db: Session,
        mapping_id: str,
        version_number: int,
        change_summary: Optional[str] = None,
        snapshot_json: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> MappingVersion:
        mv = MappingVersion(
            mapping_id=mapping_id,
            version_number=version_number,
            status="DRAFT",
            change_summary=change_summary,
            snapshot_json=snapshot_json,
            created_by=created_by
        )
        db.add(mv)
        db.commit()
        db.refresh(mv)
        return mv

    def list_versions(self, db: Session, mapping_id: str) -> List[MappingVersion]:
        return db.query(MappingVersion).filter(MappingVersion.mapping_id == mapping_id).order_by(MappingVersion.version_number.desc()).all()

    def create_field_rule(
        self,
        db: Session,
        mapping_id: str,
        source_field: str,
        target_field: str,
        source_data_type: str = "STRING",
        target_data_type: str = "STRING",
        is_required: bool = False,
        default_value: Optional[str] = None,
        transformation_type: str = "NONE",
        transformation_config_json: Optional[str] = None,
        sort_order: int = 0,
        mapping_version_id: Optional[str] = None
    ) -> MappingFieldRule:
        rule = MappingFieldRule(
            mapping_id=mapping_id,
            mapping_version_id=mapping_version_id,
            source_field=source_field,
            target_field=target_field,
            source_data_type=source_data_type.upper(),
            target_data_type=target_data_type.upper(),
            is_required=is_required,
            default_value=default_value,
            transformation_type=transformation_type.upper(),
            transformation_config_json=transformation_config_json,
            sort_order=sort_order,
            is_active=True
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    def get_field_rule_or_raise(self, db: Session, field_rule_id: str) -> MappingFieldRule:
        rule = db.query(MappingFieldRule).filter(MappingFieldRule.id == field_rule_id).first()
        if not rule:
            raise NotFoundException(f"Field mapping rule '{field_rule_id}' not found.")
        return rule

    def list_field_rules(self, db: Session, mapping_id: str) -> List[MappingFieldRule]:
        return db.query(MappingFieldRule).filter(
            MappingFieldRule.mapping_id == mapping_id,
            MappingFieldRule.is_active == True
        ).order_by(MappingFieldRule.sort_order.asc()).all()

    def delete_field_rule(self, db: Session, field_rule_id: str) -> bool:
        rule = db.query(MappingFieldRule).filter(MappingFieldRule.id == field_rule_id).first()
        if rule:
            db.delete(rule)
            db.commit()
            return True
        return False

    def log_validation(
        self,
        db: Session,
        mapping_id: str,
        validation_result: Dict[str, Any]
    ) -> MappingValidationLog:
        log = MappingValidationLog(
            mapping_id=mapping_id,
            overall_status=validation_result["status"],
            errors_json=json.dumps(validation_result.get("errors", [])),
            warnings_json=json.dumps(validation_result.get("warnings", [])),
            mapped_fields_count=len(validation_result.get("mapped_fields", [])),
            unmapped_required_count=len(validation_result.get("unmapped_required_fields", [])),
            unmapped_optional_count=len(validation_result.get("unmapped_optional_fields", []))
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def _to_dict(self, m: MappingDefinition) -> Dict[str, Any]:
        return {
            "id": m.id,
            "name": m.name,
            "source_connector_id": m.source_connector_id,
            "source_company_identifier": m.source_company_identifier,
            "target_connector_id": m.target_connector_id,
            "target_company_identifier": m.target_company_identifier,
            "canonical_entity_type": m.canonical_entity_type,
            "status": m.status,
            "current_version": m.current_version,
            "description": m.description,
            "created_by": m.created_by,
            "updated_by": m.updated_by,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None
        }

mapping_repository = MappingRepository()
