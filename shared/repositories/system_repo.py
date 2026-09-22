"""
CtrlBooks - ActivityLog, Notification, Settings & HealthHistory Repositories
---------------------------------------------------------------------------------------
Data access layer for system activity history, user notifications, application settings, and health check history.
"""

import json
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from shared.db.models.system import ActivityLog, Notification, ApplicationSetting, HealthHistory
from shared.repositories.base import BaseRepository

class ActivityLogRepository(BaseRepository[ActivityLog]):
    def __init__(self):
        super().__init__(ActivityLog)

    def log_activity(
        self,
        db: Session,
        event_type: str,
        status: str,
        message: str,
        user_id: Optional[str] = None,
        connector_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> ActivityLog:
        log = ActivityLog(
            event_type=event_type,
            status=status,
            message=message,
            user_id=user_id,
            connector_id=connector_id,
            request_id=request_id
        )
        return self.create(db, log)

class NotificationRepository(BaseRepository[Notification]):
    def __init__(self):
        super().__init__(Notification)

    def list_unread(self, db: Session, user_id: Optional[str] = None) -> List[Notification]:
        stmt = select(Notification).where(Notification.is_read == False)
        if user_id:
            stmt = stmt.where(Notification.user_id == user_id)
        stmt = stmt.order_by(Notification.created_at.desc())
        return list(db.scalars(stmt).all())

class SettingsRepository(BaseRepository[ApplicationSetting]):
    def __init__(self):
        super().__init__(ApplicationSetting)

    def get_setting(self, db: Session, key: str, scope: str = "GLOBAL") -> Optional[Any]:
        stmt = select(ApplicationSetting).where(
            ApplicationSetting.scope == scope,
            ApplicationSetting.key == key
        )
        setting = db.scalar(stmt)
        if not setting:
            return None
        try:
            return json.loads(setting.value_json)
        except Exception:
            return setting.value_json

    def set_setting(self, db: Session, key: str, value: Any, scope: str = "GLOBAL", updated_by: Optional[str] = None) -> ApplicationSetting:
        stmt = select(ApplicationSetting).where(
            ApplicationSetting.scope == scope,
            ApplicationSetting.key == key
        )
        setting = db.scalar(stmt)
        val_json = json.dumps(value)
        if setting:
            setting.value_json = val_json
            setting.updated_by = updated_by
            db.flush()
            return setting
        else:
            new_setting = ApplicationSetting(
                scope=scope,
                key=key,
                value_json=val_json,
                updated_by=updated_by
            )
            return self.create(db, new_setting)

class HealthHistoryRepository(BaseRepository[HealthHistory]):
    def __init__(self):
        super().__init__(HealthHistory)

    def record_health(
        self,
        db: Session,
        component: str,
        status: str,
        latency_ms: int = 0,
        details: Optional[Dict[str, Any]] = None
    ) -> HealthHistory:
        hh = HealthHistory(
            component=component,
            status=status,
            latency_ms=latency_ms,
            details_json=json.dumps(details) if details else None
        )
        return self.create(db, hh)
