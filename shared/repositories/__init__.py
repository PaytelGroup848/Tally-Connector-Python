"""
CtrlBooks - Repository Data Access Layer Package Index
-------------------------------------------------------------------
Exports all entity repositories for clean data access across services.
"""

from shared.repositories.base import BaseRepository
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.permission_repo import PermissionRepository, RolePermissionRepository
from shared.repositories.connector_repo import (
    DataSourceRepository,
    DestinationRepository,
    ConnectorRepository,
    FieldMappingRepository,
    mask_config_dict,
)
from shared.repositories.sync_repo import (
    SyncJobRepository,
    SyncErrorRepository,
    SyncCheckpointRepository,
)
from shared.repositories.system_repo import (
    ActivityLogRepository,
    NotificationRepository,
    SettingsRepository,
    HealthHistoryRepository,
)
from shared.repositories.mapping_repo import MappingRepository, mapping_repository
from shared.repositories.extraction_repo import ExtractionRunRepository, extraction_run_repository
from shared.repositories.storage_repo import ExtractedRecordRepository, extracted_record_repository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "RoleRepository",
    "PermissionRepository",
    "RolePermissionRepository",
    "DataSourceRepository",
    "DestinationRepository",
    "ConnectorRepository",
    "FieldMappingRepository",
    "mask_config_dict",
    "SyncJobRepository",
    "SyncErrorRepository",
    "SyncCheckpointRepository",
    "ActivityLogRepository",
    "NotificationRepository",
    "SettingsRepository",
    "HealthHistoryRepository",
    "MappingRepository",
    "mapping_repository",
    "ExtractionRunRepository",
    "extraction_run_repository",
    "ExtractedRecordRepository",
    "extracted_record_repository",
]
