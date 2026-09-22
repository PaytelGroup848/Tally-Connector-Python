

import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from shared.db.models.connector import Connector
from shared.repositories.connector_repo import ConnectorRepository
from shared.repositories.system_repo import ActivityLogRepository
from apps.backend.adapters.registry import connector_registry
from shared.exceptions import ValidationError, NotFoundException, ConflictException
from shared.db.base import utc_now
from shared.logging_config import get_logger

logger = get_logger("app.services.connector")

class ConnectorService:
    def __init__(self):
        self.connector_repo = ConnectorRepository()
        self.audit_repo = ActivityLogRepository()

    def list_connectors(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        connector_type: Optional[str] = None,
        status: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Dict[str, Any]:
        """List paginated connectors with search, type, status, and active filters."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        skip = (page - 1) * page_size

        connectors = self.connector_repo.list_connectors(
            db, skip=skip, limit=page_size, search=search,
            connector_type=connector_type, status=status, is_active=is_active
        )
        total = self.connector_repo.count_connectors(
            db, search=search, connector_type=connector_type, status=status, is_active=is_active
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        items = [self._format_connector_dict(c) for c in connectors]
        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }

    def get_connector_by_id(self, db: Session, connector_id: str) -> Dict[str, Any]:
        """Fetch connector by ID and return safe dictionary with secrets masked."""
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.deleted_at:
            raise NotFoundException(f"Connector '{connector_id}' has been deleted.")
        return self._format_connector_dict(connector)

    def create_connector(
        self,
        db: Session,
        name: str,
        connector_type: str,
        configuration: Dict[str, Any],
        description: Optional[str] = None,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Creates a new connector, validates configuration via registered adapter, and stores safe JSON."""
        clean_name = name.strip()
        clean_type = connector_type.strip().upper()

        if not clean_name or len(clean_name) < 2 or len(clean_name) > 150:
            raise ValidationError("Connector name must be between 2 and 150 characters long.")

        if self.connector_repo.get_by_name(db, clean_name):
            raise ConflictException(f"Connector with name '{clean_name}' already exists.")

        adapter = connector_registry.get_adapter(clean_type)
        valid_config = adapter.validate_configuration(configuration)

        new_connector = Connector(
            name=clean_name,
            connector_type=clean_type,
            description=description.strip() if description else None,
            configuration_json=json.dumps(valid_config),
            configuration_status="CONFIGURED",
            connection_status="UNKNOWN",
            status="DRAFT",
            is_active=False,
            created_by=acting_user_id,
            updated_by=acting_user_id
        )

        created_connector = self.connector_repo.create(db, new_connector)
        self._log_audit(db, acting_user_id, created_connector.id, "CONNECTOR_CREATED", f"Created '{clean_name}' ({clean_type})", request_id)

        logger.info(f"Connector '{clean_name}' ({clean_type}) created successfully")
        return self._format_connector_dict(created_connector)

    def update_connector(
        self,
        db: Session,
        connector_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        configuration: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """
        Updates connector details or configuration.
        Critical Rule: If connection configuration changes, resets connection_status to 'UNKNOWN'.
        """
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.deleted_at:
            raise NotFoundException(f"Connector '{connector_id}' has been deleted.")

        update_fields = {"updated_by": acting_user_id}

        if name and name.strip():
            c_name = name.strip()
            existing = self.connector_repo.get_by_name(db, c_name)
            if existing and existing.id != connector.id:
                raise ConflictException(f"Connector name '{c_name}' is already used by another pipeline.")
            update_fields["name"] = c_name

        if description is not None:
            update_fields["description"] = description.strip()

        config_changed = False
        if configuration is not None:
            adapter = connector_registry.get_adapter(connector.connector_type)
            valid_config = adapter.validate_configuration(configuration)
            update_fields["configuration_json"] = json.dumps(valid_config)
            update_fields["configuration_status"] = "CONFIGURED"
            
            update_fields["connection_status"] = "UNKNOWN"
            config_changed = True

        if is_active is not None:
            update_fields["is_active"] = is_active
            update_fields["status"] = "ACTIVE" if is_active else "INACTIVE"

        updated = self.connector_repo.update(db, connector, update_fields)
        
        msg = f"Updated connector '{updated.name}'"
        if config_changed:
            msg += " (Configuration updated - connection status reset to UNKNOWN)"

        self._log_audit(db, acting_user_id, updated.id, "CONNECTOR_UPDATED", msg, request_id)
        return self._format_connector_dict(updated)

    def set_connector_activation(
        self,
        db: Session,
        connector_id: str,
        active: bool,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Activates or deactivates a connector pipeline."""
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.deleted_at:
            raise NotFoundException("Connector has been deleted.")

        if active and connector.configuration_status != "CONFIGURED":
            raise ValidationError("Cannot activate connector with invalid or missing configuration.")

        update_fields = {
            "is_active": active,
            "status": "ACTIVE" if active else "INACTIVE",
            "updated_by": acting_user_id
        }
        updated = self.connector_repo.update(db, connector, update_fields)

        event = "CONNECTOR_ACTIVATED" if active else "CONNECTOR_DEACTIVATED"
        self._log_audit(db, acting_user_id, updated.id, event, f"Set activation status to {active} for '{updated.name}'", request_id)
        return self._format_connector_dict(updated)

    def test_connector_connection(
        self,
        db: Session,
        connector_id: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """
        Executes truthful connection test via registered connector adapter.
        Updates last_tested_at, connection_status, and last_error_message in DB.
        """
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.deleted_at:
            raise NotFoundException("Connector has been deleted.")

        adapter = connector_registry.get_adapter(connector.connector_type)
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=False)

        self.connector_repo.update(db, connector, {"connection_status": "TESTING"})

        test_result = adapter.test_connection(raw_config, timeout=5)

        now = utc_now()
        update_fields = {
            "last_tested_at": now,
            "connection_status": test_result["status"]
        }

        if test_result["status"] == "CONNECTED":
            update_fields["last_connected_at"] = now
            update_fields["last_error_message"] = None
        else:
            update_fields["last_error_message"] = test_result.get("message") or test_result.get("error")

        updated = self.connector_repo.update(db, connector, update_fields)

        self._log_audit(
            db=db,
            acting_user_id=acting_user_id,
            connector_id=updated.id,
            event_type="CONNECTOR_TESTED",
            message=f"Tested connection for '{updated.name}' - Result: {test_result['status']}",
            request_id=request_id
        )

        return {
            "connector_id": updated.id,
            "connector_name": updated.name,
            "connector_type": updated.connector_type,
            "status": test_result["status"],
            "message": test_result["message"],
            "latency_ms": test_result.get("latency_ms"),
            "tested_at": now.isoformat()
        }

    def delete_connector(self, db: Session, connector_id: str, acting_user_id: Optional[str] = None, request_id: str = "") -> bool:
        """Soft deletes connector pipeline."""
        connector = self.connector_repo.get_by_id_or_raise(db, connector_id)
        if connector.deleted_at:
            return True

        self.connector_repo.delete(db, connector.id, hard=False)
        self._log_audit(db, acting_user_id, connector.id, "CONNECTOR_DELETED", f"Soft deleted connector '{connector.name}'", request_id)
        logger.info(f"Connector '{connector.name}' soft deleted successfully")
        return True

    def _format_connector_dict(self, connector: Connector) -> Dict[str, Any]:
        raw_config = self.connector_repo.get_configuration(connector, mask_secrets=True)
        return {
            "id": connector.id,
            "name": connector.name,
            "connector_type": connector.connector_type,
            "description": connector.description,
            "configuration_status": connector.configuration_status,
            "connection_status": connector.connection_status,
            "status": connector.status,
            "is_active": connector.is_active,
            "configuration": raw_config,
            "last_tested_at": connector.last_tested_at.isoformat() if connector.last_tested_at else None,
            "last_connected_at": connector.last_connected_at.isoformat() if connector.last_connected_at else None,
            "last_sync_at": connector.last_sync_at.isoformat() if connector.last_sync_at else None,
            "last_error_message": connector.last_error_message,
            "created_at": connector.created_at.isoformat() if connector.created_at else None,
            "updated_at": connector.updated_at.isoformat() if connector.updated_at else None,
        }

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
            logger.error(f"Failed to record connector audit event: {exc}")

connector_service = ConnectorService()
