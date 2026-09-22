

import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from shared.repositories.connector_repo import ConnectorRepository
from shared.repositories.extraction_repo import ExtractionRunRepository
from shared.repositories.storage_repo import extracted_record_repository
from shared.repositories.mapping_repo import MappingRepository
from shared.repositories.system_repo import ActivityLogRepository
from shared.mapping.canonical_registry import canonical_registry
from shared.extraction.filter_registry import extraction_filter_registry
from shared.extraction.validation_service import canonical_record_validation_service
from shared.extraction.tally_extractor import tally_data_extractor
from shared.extraction.base import CanonicalDataRecord
from apps.backend.services.mapping_service import MappingService
from shared.exceptions import (
    ValidationError, NotFoundException, ConflictException
)
from shared.logging_config import get_logger

logger = get_logger("app.services.extraction")

class ExtractionService:
    def __init__(self):
        self.connector_repo = ConnectorRepository()
        self.extraction_repo = ExtractionRunRepository()
        self.mapping_repo = MappingRepository()
        self.audit_repo = ActivityLogRepository()
        self.mapping_service = MappingService()

    def extract_entity(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
        cursor: Optional[str] = None,
        mapping_id: Optional[str] = None,
        store_in_db: bool = False,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes single entity type extraction with optional Module 9 mapping transformation preview.
        Enforces read-only safety with zero target system writes.
        """
        connector = self._validate_connector_and_company(db, connector_id, company_identifier)
        clean_entity = self._validate_entity_and_capability(connector, entity_type)
        valid_page_size = extraction_filter_registry.validate_page_size(page_size, is_preview=False)
        clean_filters = extraction_filter_registry.validate_filters(clean_entity, filters)

        active_run = self.extraction_repo.find_active_run(db, connector_id, company_identifier, clean_entity)
        if active_run:
            raise ConflictException(f"An extraction run (ID: {active_run.id}) is already in progress for connector '{connector_id}', company '{company_identifier}', entity '{clean_entity}'.")

        mapping_obj = None
        mode = "CANONICAL"
        if mapping_id:
            mapping_obj = self._validate_mapping_scope(db, mapping_id, connector, company_identifier, clean_entity)
            mode = "MAPPED_PREVIEW"

        run = self.extraction_repo.create_run(
            db=db,
            connector_id=connector_id,
            company_identifier=company_identifier,
            entity_type=clean_entity,
            filters=clean_filters,
            mapping_id=mapping_id,
            mode=mode,
            created_by=user_id
        )

        extractor = tally_data_extractor
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)
        raw_config["connector_id"] = connector.id

        try:
            extraction_res = extractor.extract(
                connector_config=raw_config,
                company_identifier=company_identifier,
                canonical_entity_type=clean_entity,
                filters=clean_filters,
                cursor=cursor,
                page_size=valid_page_size
            )

            raw_records: List[CanonicalDataRecord] = extraction_res.get("records", [])
            ext_status = extraction_res.get("status", "SUCCESS")
            next_cursor = extraction_res.get("next_cursor")

            if ext_status == "SOURCE_UNAVAILABLE":
                self.extraction_repo.update_run_status(
                    db, run.id, "FAILED", error_code="SOURCE_UNAVAILABLE", error_message=extraction_res.get("error")
                )
                db.commit()
                return {
                    "success": False,
                    "run_id": run.id,
                    "error": {"code": "SOURCE_UNAVAILABLE", "message": extraction_res.get("error") or "Source system unavailable"}
                }

            valid_records, failed_details, valid_cnt, failed_cnt = canonical_record_validation_service.process_records(raw_records)

            processed_output_records = []
            if mapping_obj and valid_records:
                for rec in valid_records:
                    preview_res = self.mapping_service.preview_mapping(
                        db=db,
                        mapping_id=mapping_obj.id,
                        source_record=rec.data
                    )
                    processed_output_records.append({
                        "record_id": rec.record_id,
                        "source_identifier": rec.source_identifier,
                        "canonical_data": rec.data,
                        "mapped_data": preview_res.get("target_preview", {}),
                        "applied_transformations": preview_res.get("applied_transformations", [])
                    })
            else:
                processed_output_records = [r.to_dict() for r in valid_records]

            final_status = "SUCCESS"
            if failed_cnt > 0 and valid_cnt > 0:
                final_status = "PARTIAL_SUCCESS"
            elif valid_cnt == 0:
                final_status = "EMPTY" if not raw_records else "FAILED"

            self.extraction_repo.update_run_status(
                db=db,
                run_id=run.id,
                status=final_status,
                records_requested=valid_page_size,
                records_returned=len(processed_output_records),
                records_normalized=valid_cnt,
                records_failed=failed_cnt
            )
            
            if store_in_db and processed_output_records:
                try:
                    extracted_record_repository.upsert_batch(
                        db=db,
                        connector_id=connector_id,
                        company_identifier=company_identifier,
                        entity_type=clean_entity,
                        records=processed_output_records
                    )
                except Exception as exc:
                    logger.warning(f"Failed to persist extracted records to DB storage: {exc}")

            db.commit()

            self.audit_repo.log_activity(
                db=db,
                event_type="DATA_EXTRACTION_COMPLETED",
                connector_id=connector_id,
                user_id=user_id,
                status=final_status,
                message=f"Extracted {valid_cnt} records ({failed_cnt} failed) for entity '{clean_entity}' (Mode: {mode})"
            )

            return {
                "success": True,
                "data": {
                    "run_id": run.id,
                    "connector_id": connector_id,
                    "company_identifier": company_identifier,
                    "entity_type": clean_entity,
                    "mode": mode,
                    "status": final_status,
                    "records": processed_output_records,
                    "failed_records": failed_details if failed_cnt > 0 else [],
                    "pagination": {
                        "page_size": valid_page_size,
                        "returned": len(processed_output_records),
                        "failed": failed_cnt,
                        "next_cursor": next_cursor
                    }
                }
            }

        except Exception as exc:
            db.rollback()
            logger.error(f"Extraction execution error: {exc}")
            self.extraction_repo.update_run_status(
                db, run.id, "FAILED", error_code="EXTRACTION_FAILED", error_message=str(exc)
            )
            db.commit()
            raise ValidationError(f"Data extraction failed: {exc}")

    def preview_extraction(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        entity_type: str,
        mapping_id: Optional[str] = None,
        limit: int = 10,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes a safe read-only preview extraction bounded by small limits (max 50)."""
        valid_limit = extraction_filter_registry.validate_page_size(limit, is_preview=True)
        res = self.extract_entity(
            db=db,
            connector_id=connector_id,
            company_identifier=company_identifier,
            entity_type=entity_type,
            filters=None,
            page_size=valid_limit,
            cursor=None,
            mapping_id=mapping_id,
            user_id=user_id
        )

        if res.get("success") and "data" in res:
            res["data"]["is_preview"] = True
            res["data"]["notice"] = "PREVIEW ONLY — No target database or API records created/updated."
        return res

    def get_single_record(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        entity_type: str,
        source_identifier: str
    ) -> Dict[str, Any]:
        """Extracts a single source record by primary identifier."""
        connector = self._validate_connector_and_company(db, connector_id, company_identifier)
        clean_entity = self._validate_entity_and_capability(connector, entity_type)

        extractor = tally_data_extractor
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)
        raw_config["connector_id"] = connector.id

        rec = extractor.extract_single(
            connector_config=raw_config,
            company_identifier=company_identifier,
            canonical_entity_type=clean_entity,
            source_identifier=source_identifier
        )

        if not rec:
            raise NotFoundException(f"Record with identifier '{source_identifier}' not found in source for entity '{clean_entity}'.")

        return {
            "success": True,
            "data": rec.to_dict()
        }

    def list_history(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        connector_id: Optional[str] = None,
        company_identifier: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lists extraction run history with pagination and filters."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        skip = (page - 1) * page_size

        runs = self.extraction_repo.list_runs(
            db, skip=skip, limit=page_size,
            connector_id=connector_id, company_identifier=company_identifier,
            entity_type=entity_type, status=status
        )
        total = self.extraction_repo.count_runs(
            db, connector_id=connector_id, company_identifier=company_identifier,
            entity_type=entity_type, status=status
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        items = [
            {
                "run_id": r.id,
                "connector_id": r.connector_id,
                "company_identifier": r.company_identifier,
                "entity_type": r.entity_type,
                "mapping_id": r.mapping_id,
                "mode": r.mode,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "records_requested": r.records_requested,
                "records_returned": r.records_returned,
                "records_normalized": r.records_normalized,
                "records_failed": r.records_failed,
                "error_code": r.error_code,
                "error_message": r.error_message
            }
            for r in runs
        ]

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }

    def get_run_details(self, db: Session, run_id: str) -> Dict[str, Any]:
        """Retrieves details of a specific extraction run."""
        r = self.extraction_repo.get_by_id_or_raise(db, run_id)
        return {
            "run_id": r.id,
            "connector_id": r.connector_id,
            "company_identifier": r.company_identifier,
            "entity_type": r.entity_type,
            "filters": json.loads(r.filters_json) if r.filters_json else {},
            "mapping_id": r.mapping_id,
            "mode": r.mode,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "records_requested": r.records_requested,
            "records_returned": r.records_returned,
            "records_normalized": r.records_normalized,
            "records_failed": r.records_failed,
            "error_code": r.error_code,
            "error_message": r.error_message
        }

    def _validate_connector_and_company(self, db: Session, connector_id: str, company_identifier: str) -> Any:
        connector = self.connector_repo.get_by_id(db, connector_id)
        if not connector or connector.deleted_at is not None:
            raise NotFoundException(f"Connector '{connector_id}' not found.")
        if not connector.is_active:
            raise ValidationError(f"Connector '{connector.name}' is currently INACTIVE.")
        if not company_identifier or not company_identifier.strip():
            raise ValidationError("Company identifier context is required for data extraction.")
        return connector

    def _validate_entity_and_capability(self, connector: Any, entity_type: str) -> str:
        clean_entity = (entity_type or "").strip().upper()
        if not canonical_registry.is_entity_type_supported(clean_entity):
            raise ValidationError(f"Unsupported canonical entity type '{entity_type}'.")
        
        src_type = connector.connector_type.upper()
        supported_src_fields = canonical_registry.get_supported_source_fields(src_type, clean_entity)
        if not supported_src_fields:
            raise ValidationError(f"Connector type '{src_type}' does not support entity type '{clean_entity}'.")
        return clean_entity

    def _validate_mapping_scope(self, db: Session, mapping_id: str, connector: Any, company_identifier: str, clean_entity: str) -> Any:
        mapping = self.mapping_repo.get_by_id(db, mapping_id)
        if not mapping or mapping.deleted_at is not None:
            raise NotFoundException(f"Mapping definition '{mapping_id}' not found.")
        if mapping.status != "ACTIVE":
            raise ValidationError(f"Mapping definition '{mapping.name}' is not ACTIVE.")
        if mapping.source_connector_id != connector.id:
            raise ValidationError(f"Mapping '{mapping.name}' source connector mismatch.")
        if mapping.source_company_identifier.strip().lower() != company_identifier.strip().lower():
            raise ValidationError(f"Mapping '{mapping.name}' source company scope mismatch.")
        if mapping.canonical_entity_type.upper() != clean_entity:
            raise ValidationError(f"Mapping '{mapping.name}' entity type mismatch ({mapping.canonical_entity_type} vs {clean_entity}).")
        return mapping

extraction_service = ExtractionService()
