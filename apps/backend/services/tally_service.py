"""
CtrlBooks - Tally Integration Business Service
----------------------------------------------------------
Business logic for discovering companies from running Tally instances, validating company selection,
binding target companies to connector pipelines, discovering metadata, and recording audit events.
"""

import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from shared.repositories.connector_repo import ConnectorRepository
from shared.repositories.system_repo import ActivityLogRepository
from apps.backend.adapters.registry import connector_registry
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.services.tally")

class TallyService:
    def __init__(self):
        self.connector_repo = ConnectorRepository()
        self.audit_repo = ActivityLogRepository()

    async def get_tally_companies(
        self,
        db: Session,
        connector_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Queries running Tally Prime instance and returns open company list."""
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.connector_type != "TALLY":
            raise ValidationError(f"Connector '{connector_id}' is of type '{connector.connector_type}', not TALLY.")

        adapter = connector_registry.get_adapter("TALLY")
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)

        try:
            companies = await adapter.discover_companies(raw_config)
            self._log_audit(db, acting_user_id, connector.id, "TALLY_COMPANY_DISCOVERY_SUCCEEDED", f"Discovered {len(companies)} open Tally companies", request_id)
            return companies
        except Exception as exc:
            self._log_audit(db, acting_user_id, connector.id, "TALLY_COMPANY_DISCOVERY_FAILED", f"Company discovery failed: {exc}", request_id)
            raise

    async def select_tally_company(
        self,
        db: Session,
        connector_id: str,
        company_name: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """
        Re-validates company_name against real Tally open company list before storing into connector configuration.
        """
        clean_company = (company_name or "").strip()
        if not clean_company:
            raise ValidationError("Target Tally company name is required.")

        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.connector_type != "TALLY":
            raise ValidationError(f"Connector '{connector_id}' is of type '{connector.connector_type}', not TALLY.")

        open_companies = await self.get_tally_companies(db, connector_id, acting_user_id, request_id)
        found_comp = next((c for c in open_companies if c["name"].lower() == clean_company.lower()), None)
        if not found_comp:
            names = [c["name"] for c in open_companies]
            raise ValidationError(f"Company '{clean_company}' is not open in Tally Prime. Open companies: {names or 'None'}")

        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)
        raw_config["company_name"] = found_comp["name"]
        if found_comp.get("guid"):
            raw_config["company_guid"] = found_comp["guid"]

        updated = self.connector_repo.update(db, connector, {
            "configuration_json": json.dumps(raw_config),
            "configuration_status": "CONFIGURED",
            "updated_by": acting_user_id
        })

        self._log_audit(db, acting_user_id, updated.id, "TALLY_COMPANY_SELECTED", f"Selected Tally company '{found_comp['name']}'", request_id)
        logger.info(f"Tally company '{found_comp['name']}' bound to connector '{updated.name}'")

        return {
            "connector_id": updated.id,
            "connector_name": updated.name,
            "selected_company": found_comp["name"],
            "company_guid": found_comp.get("guid"),
            "configuration_status": updated.configuration_status
        }

    async def get_tally_metadata(
        self,
        db: Session,
        connector_id: str,
        metadata_type: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Queries metadata from Tally instance for allowed metadata types."""
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.connector_type != "TALLY":
            raise ValidationError(f"Connector '{connector_id}' is of type '{connector.connector_type}', not TALLY.")

        adapter = connector_registry.get_adapter("TALLY")
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)

        try:
            items = await adapter.discover_metadata(raw_config, metadata_type)
            self._log_audit(db, acting_user_id, connector.id, "TALLY_METADATA_DISCOVERY_SUCCEEDED", f"Discovered {len(items)} {metadata_type} records from Tally", request_id)
            return {
                "connector_id": connector.id,
                "connector_name": connector.name,
                "metadata_type": metadata_type,
                "total_count": len(items),
                "items": items
            }
        except Exception as exc:
            self._log_audit(db, acting_user_id, connector.id, "TALLY_METADATA_DISCOVERY_FAILED", f"Metadata discovery failed for {metadata_type}: {exc}", request_id)
            raise

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
            logger.error(f"Failed to record Tally audit event: {exc}")

tally_service = TallyService()
