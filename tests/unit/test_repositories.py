"""
Unit tests for Repository Data Access Layer and Transaction Rollback
"""

import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.db.base import Base
from shared.db.models import User, Role, DataSource, Destination, Connector, ApplicationSetting
from shared.repositories import (
    UserRepository,
    RoleRepository,
    DataSourceRepository,
    DestinationRepository,
    ConnectorRepository,
    SettingsRepository,
)
from shared.exceptions import ConflictException, NotFoundException

class TestRepositories(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_user_repo_crud_and_unique_constraint(self):
        repo = UserRepository()
        u1 = User(username="alice", full_name="Alice Smith", email="alice@example.com", password_hash="hashed123")
        created = repo.create(self.db, u1)
        self.db.commit()

        self.assertIsNotNone(created.id)
        fetched = repo.get_by_email(self.db, "alice@example.com")
        self.assertEqual(fetched.full_name, "Alice Smith")

        u2 = User(username="duplicate_alice", full_name="Duplicate Alice", email="alice@example.com", password_hash="hashed456")
        with self.assertRaises(ConflictException):
            repo.create(self.db, u2)

    def test_soft_delete(self):
        repo = DataSourceRepository()
        ds = repo.create_source(self.db, "Tally Server", "TALLY", {"host": "127.0.0.1", "port": 9000})
        self.db.commit()

        source_id = ds.id
        self.assertIsNotNone(repo.get_by_id(self.db, source_id))

        deleted = repo.delete(self.db, source_id, hard=False)
        self.db.commit()
        self.assertTrue(deleted)

        self.assertIsNone(repo.get_by_id(self.db, source_id))
        self.assertEqual(len(repo.list_all(self.db, include_deleted=True)), 1)

    def test_secret_masking(self):
        repo = DataSourceRepository()
        ds = repo.create_source(
            self.db,
            "REST API Source",
            "REST_API",
            {"endpoint": "https://api.example.com", "API_KEY": "secret-api-key-999"}
        )
        self.db.commit()

        masked = repo.get_configuration(ds, mask_secrets=True)
        self.assertEqual(masked["API_KEY"], "****")
        self.assertEqual(masked["endpoint"], "https://api.example.com")

    def test_settings_repo(self):
        repo = SettingsRepository()
        repo.set_setting(self.db, "theme", "dark", scope="SYSTEM")
        self.db.commit()

        val = repo.get_setting(self.db, "theme", scope="SYSTEM")
        self.assertEqual(val, "dark")

if __name__ == "__main__":
    unittest.main()
