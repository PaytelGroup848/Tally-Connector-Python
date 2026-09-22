"""
CtrlBooks - SQLAlchemy ORM Models Package Index
------------------------------------------------------------
Exports all core schema models for database registration and migrations.
Must strictly stay under 150 lines of code.
"""

from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, utc_now
from shared.db.models.user import User, Role, UserRole, Permission, RolePermission
from shared.db.models.connector import DataSource, Destination, Connector, FieldMapping
from shared.db.models.sync import SyncJobV2, SyncError, SyncCheckpoint, SyncQueue
from shared.db.models.system import ActivityLog, Notification, ApplicationSetting, HealthHistory
from shared.db.models.metadata import UnifiedSourceMetadata, MetadataDiscoveryRun
from shared.db.models.mapping import MappingDefinition, MappingVersion, MappingFieldRule, MappingValidationLog
from shared.db.models.extraction import DataExtractionRun
from shared.db.models.storage import ExtractedRecord
from shared.db.models.company import CompanySyncConfig

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "utc_now",
    "User",
    "Role",
    "UserRole",
    "Permission",
    "RolePermission",
    "DataSource",
    "Destination",
    "Connector",
    "FieldMapping",
    "MappingDefinition",
    "MappingVersion",
    "MappingFieldRule",
    "MappingValidationLog",
    "DataExtractionRun",
    "ExtractedRecord",
    "SyncJobV2",
    "SyncError",
    "SyncCheckpoint",
    "SyncQueue",
    "ActivityLog",
    "Notification",
    "ApplicationSetting",
    "HealthHistory",
    "UnifiedSourceMetadata",
    "MetadataDiscoveryRun",
    "CompanySyncConfig",
]
