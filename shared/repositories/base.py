"""
CtrlBooks - Generic Base Repository
------------------------------------------------
Type-safe generic repository providing CRUD operations, soft-delete filtering,
pagination, transaction safety, and DB exception handling.
"""

from typing import Generic, TypeVar, Type, Optional, List, Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from shared.exceptions import AppException, NotFoundException, ConflictException
from shared.logging_config import get_logger

T = TypeVar("T")
logger = get_logger("app.repositories")

class BaseRepository(Generic[T]):
    """Generic repository providing standardized data access for SQLAlchemy models."""
    def __init__(self, model: Type[T]):
        self.model = model

    def get_by_id(self, db: Session, id: Any) -> Optional[T]:
        """Fetch record by primary key, excluding soft-deleted items if applicable."""
        stmt = select(self.model).where(self.model.id == id)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return db.scalar(stmt)

    def get_by_id_or_raise(self, db: Session, id: Any) -> T:
        """Fetch record by primary key or raise NotFoundException."""
        obj = self.get_by_id(db, id)
        if not obj:
            raise NotFoundException(f"{self.model.__name__} with ID '{id}' not found")
        return obj

    def list_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        include_deleted: bool = False
    ) -> List[T]:
        """List records with optional filtering and pagination."""
        stmt = select(self.model)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    stmt = stmt.where(getattr(self.model, key) == value)

        stmt = stmt.offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    def count(self, db: Session, filters: Optional[Dict[str, Any]] = None, include_deleted: bool = False) -> int:
        """Count total matching records."""
        stmt = select(func.count()).select_from(self.model)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    stmt = stmt.where(getattr(self.model, key) == value)

        return db.scalar(stmt) or 0

    def create(self, db: Session, obj: T) -> T:
        """Persist a new entity instance."""
        try:
            db.add(obj)
            db.flush()
            return obj
        except IntegrityError as exc:
            db.rollback()
            logger.warning(f"Integrity violation creating {self.model.__name__}: {exc}")
            raise ConflictException(f"Resource already exists or violates constraint: {exc.orig}")
        except Exception as exc:
            db.rollback()
            logger.error(f"Error creating {self.model.__name__}: {exc}")
            raise AppException(f"Failed to create {self.model.__name__}: {exc}")

    def update(self, db: Session, db_obj: T, update_data: Dict[str, Any]) -> T:
        """Update an existing entity with field values."""
        try:
            for field, val in update_data.items():
                if hasattr(db_obj, field):
                    setattr(db_obj, field, val)
            db.flush()
            return db_obj
        except IntegrityError as exc:
            db.rollback()
            raise ConflictException(f"Update constraint violation: {exc.orig}")
        except Exception as exc:
            db.rollback()
            raise AppException(f"Failed to update {self.model.__name__}: {exc}")

    def delete(self, db: Session, id: Any, hard: bool = False) -> bool:
        """Delete entity by ID (supports soft delete if model inherits SoftDeleteMixin)."""
        obj = self.get_by_id(db, id)
        if not obj:
            return False

        try:
            if hasattr(self.model, "deleted_at") and not hard:
                from shared.db.base import utc_now
                obj.deleted_at = utc_now()
            else:
                db.delete(obj)
            db.flush()
            return True
        except Exception as exc:
            db.rollback()
            raise AppException(f"Failed to delete {self.model.__name__}: {exc}")
