"""
CtrlBooks - Metadata Discovery & Unified Metadata Business Service
--------------------------------------------------------------------------------
Orchestrates real source metadata discovery across Tally & BUSY connectors,
validates company context, normalizes raw accounting structures to canonical entities,
handles batched upserts, reconciles stale records, and logs audit events.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from shared.repositories.connector_repo import ConnectorRepository
from shared.repositories.metadata_repo import MetadataRepository, MetadataDiscoveryRunRepository
from shared.repositories.system_repo import ActivityLogRepository
from shared.metadata.registry import MetadataRegistry
from shared.metadata.normalizers import tally_normalizer
from apps.backend.adapters.registry import connector_registry
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.services.metadata_discovery")

class MetadataDiscoveryService:
    def __init__(self):
        self.connector_repo = ConnectorRepository()
        self.meta_repo = MetadataRepository()
        self.run_repo = MetadataDiscoveryRunRepository()
        self.audit_repo = ActivityLogRepository()

    async def discover_metadata(
        self,
        db: Session,
        connector_id: str,
        entity_types: List[str],
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """
        Executes real data discovery for requested canonical entity types over target connector.
        Validates company context, normalizes source records, upserts records, and reconciles stale data.
        """
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)

        company_identifier = raw_config.get("company_name") or raw_config.get("company_code")
        if not company_identifier:
            raise ValidationError(f"Connector '{connector.name}' has no selected company bound. Please discover and select a company first.")

        allowed_cats = MetadataRegistry.get_allowed_categories()
        clean_types = []
        for et in entity_types or []:
            c = et.strip().upper()
            if c not in allowed_cats:
                raise ValidationError(f"Invalid canonical entity type '{et}'. Allowed categories: {', '.join(allowed_cats)}")
            if c not in clean_types:
                clean_types.append(c)

        if not clean_types:
            clean_types = ["LEDGER", "ACCOUNT_GROUP", "VOUCHER_TYPE", "STOCK_ITEM"]

        run = self.run_repo.create_run(db, connector.id, company_identifier, clean_types)

        adapter = connector_registry.get_adapter(connector.connector_type)
        normalizer = tally_normalizer

        total_discovered = 0
        total_created = 0
        total_updated = 0
        total_stale = 0
        total_failed = 0
        category_results = []

        try:
            for cat in clean_types:
                mapping = MetadataRegistry.get_source_mapping(cat, connector.connector_type)
                query_type = mapping["adapter_query_type"]

                try:
                    raw_items = await adapter.discover_metadata(raw_config, query_type)
                    normalized_records = normalizer.normalize(raw_items, cat, connector.id, company_identifier)

                    c_count, u_count = self.meta_repo.upsert_metadata_batch(db, normalized_records)
                    
                    current_ids = [r["source_identifier"] for r in normalized_records]
                    s_count = self.meta_repo.mark_stale_records(db, connector.id, company_identifier, cat, current_ids)

                    total_discovered += len(normalized_records)
                    total_created += c_count
                    total_updated += u_count
                    total_stale += s_count

                    category_results.append({
                        "entity_type": cat,
                        "status": "SUCCESS",
                        "discovered": len(normalized_records),
                        "created": c_count,
                        "updated": u_count,
                        "stale": s_count,
                        "failed": 0
                    })
                except Exception as cat_exc:
                    logger.warning(f"Metadata discovery failed for category '{cat}' on connector '{connector.name}': {cat_exc}")
                    total_failed += 1
                    category_results.append({
                        "entity_type": cat,
                        "status": "FAILED",
                        "error": str(cat_exc)
                    })

            final_status = "SUCCESS"
            if total_failed > 0:
                final_status = "PARTIAL_SUCCESS" if total_discovered > 0 else "FAILED"

            completed_run = self.run_repo.complete_run(
                db=db,
                run_id=run.id,
                status=final_status,
                discovered=total_discovered,
                created=total_created,
                updated=total_updated,
                stale=total_stale,
                failed=total_failed
            )

            self._log_audit(db, acting_user_id, connector.id, "METADATA_DISCOVERY_COMPLETED", f"Discovered {total_discovered} records across {len(clean_types)} categories (Created={total_created}, Updated={total_updated}, Stale={total_stale})", request_id)

            return {
                "discovery_run_id": completed_run.id,
                "connector_id": connector.id,
                "company_identifier": company_identifier,
                "status": final_status,
                "totals": {
                    "discovered": total_discovered,
                    "created": total_created,
                    "updated": total_updated,
                    "stale": total_stale,
                    "failed": total_failed
                },
                "results": category_results
            }

        except Exception as exc:
            self.run_repo.complete_run(
                db=db,
                run_id=run.id,
                status="FAILED",
                discovered=0, created=0, updated=0, stale=0, failed=len(clean_types),
                error_code="DISCOVERY_ERROR",
                error_message=str(exc)
            )
            self._log_audit(db, acting_user_id, connector.id, "METADATA_DISCOVERY_FAILED", f"Metadata discovery failed: {exc}", request_id)
            raise

    async def refresh_metadata(
        self,
        db: Session,
        connector_id: str,
        entity_types: List[str],
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Re-discovers and refreshes metadata for target connector."""
        return await self.discover_metadata(db, connector_id, entity_types, acting_user_id, request_id)

    def get_metadata_records(
        self,
        db: Session,
        connector_id: str,
        canonical_entity_type: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Lists unified metadata for a connector with pagination and filters."""
        self.connector_repo.get_by_id_or_raise(db, connector_id)
        return self.meta_repo.list_metadata(
            db=db,
            connector_id=connector_id,
            canonical_entity_type=canonical_entity_type,
            search=search,
            status=status,
            page=page,
            page_size=page_size
        )

    def get_metadata_by_id(self, db: Session, metadata_id: str) -> Dict[str, Any]:
        """Returns single unified metadata record by ID."""
        record = self.meta_repo.get_by_id_or_raise(db, metadata_id)
        return self.meta_repo._to_dict(record)

    def search_metadata(
        self,
        db: Session,
        query_str: str,
        connector_id: Optional[str] = None,
        company_identifier: Optional[str] = None,
        canonical_entity_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Global search across unified source metadata."""
        return self.meta_repo.search_metadata(
            db=db,
            query_str=query_str,
            connector_id=connector_id,
            company_identifier=company_identifier,
            canonical_entity_type=canonical_entity_type,
            page=page,
            page_size=page_size
        )

    def _log_audit(self, db: Session, acting_user_id: Optional[str], connector_id: str, event_type: str, message: str, request_id: str) -> None:
        try:
            self.audit_repo.log_activity(
                db=db,
                event_type=event_type,
                status="SUCCESS",
                message=message,
                user_id=acting_user_id,
                connector_id=connector_id,
                request_id=request_id
            )
        except Exception as exc:
            logger.error(f"Failed to log metadata audit event: {exc}")

metadata_discovery_service = MetadataDiscoveryService()
