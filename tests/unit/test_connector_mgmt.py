"""
Unit tests for Connector Management, Configuration Schemas, Adapters, and State Invalidation
"""

import unittest
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.connector import Connector
from shared.repositories.connector_repo import ConnectorRepository
from apps.backend.adapters.registry import connector_registry
from apps.backend.services.connector_service import connector_service
from shared.exceptions import ValidationError, ConflictException, NotFoundException
from scripts.seed_rbac import seed_rbac

class TestConnectorManagementUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from shared.db.models import Base
        from shared.db.session import get_engine
        Base.metadata.create_all(bind=get_engine())
        initialize_database()
        seed_rbac()

    def setUp(self):
        with get_db_session() as db:
            repo = ConnectorRepository()
            for name in ["Unit Test Tally", "Dup Connector"]:
                c = repo.get_by_name(db, name)
                if c:
                    repo.delete(db, c.id, hard=True)
            db.commit()

    def test_01_tally_configuration_validation(self):
        adapter = connector_registry.get_adapter("TALLY")
        valid_cfg = adapter.validate_configuration({"host": "127.0.0.1", "port": 9000, "connection_mode": "HTTP_XML"})
        self.assertEqual(valid_cfg["host"], "127.0.0.1")
        self.assertEqual(valid_cfg["port"], 9000)

        with self.assertRaises(ValidationError):
            adapter.validate_configuration({"host": "127.0.0.1", "port": 70000})

    def test_03_create_connector_and_duplicate_guard(self):
        with get_db_session() as db:
            c1 = connector_service.create_connector(
                db=db,
                name="Unit Test Tally",
                connector_type="TALLY",
                configuration={"host": "127.0.0.1", "port": 9000},
                description="Test Tally Connector"
            )
            self.assertEqual(c1["name"], "Unit Test Tally")
            self.assertEqual(c1["configuration_status"], "CONFIGURED")
            self.assertEqual(c1["connection_status"], "UNKNOWN")

            with self.assertRaises(ConflictException):
                connector_service.create_connector(
                    db=db,
                    name="Unit Test Tally",
                    connector_type="TALLY",
                    configuration={"host": "127.0.0.1", "port": 9000}
                )

    def test_04_state_invalidation_on_config_update(self):
        with get_db_session() as db:
            c = connector_service.create_connector(
                db=db,
                name="Unit Test Tally",
                connector_type="TALLY",
                configuration={"host": "127.0.0.1", "port": 9000}
            )
            repo = ConnectorRepository()
            conn_obj = repo.get_by_id_or_raise(db, c["id"])
            repo.update(db, conn_obj, {"connection_status": "CONNECTED"})
            db.commit()

            self.assertEqual(connector_service.get_connector_by_id(db, c["id"])["connection_status"], "CONNECTED")

            updated = connector_service.update_connector(
                db=db,
                connector_id=c["id"],
                configuration={"host": "127.0.0.1", "port": 9001}
            )
            self.assertEqual(updated["connection_status"], "UNKNOWN")

    def test_05_activation_and_deactivation(self):
        with get_db_session() as db:
            c = connector_service.create_connector(
                db=db,
                name="Unit Test Tally",
                connector_type="TALLY",
                configuration={"host": "127.0.0.1", "port": 9000}
            )

            act = connector_service.set_connector_activation(db, c["id"], active=True)
            self.assertTrue(act["is_active"])
            self.assertEqual(act["status"], "ACTIVE")

            deact = connector_service.set_connector_activation(db, c["id"], active=False)
            self.assertFalse(deact["is_active"])
            self.assertEqual(deact["status"], "INACTIVE")

    def test_06_truthful_connection_test(self):
        with get_db_session() as db:
            c = connector_service.create_connector(
                db=db,
                name="Unit Test Tally",
                connector_type="TALLY",
                configuration={"host": "127.0.0.1", "port": 59999}
            )
            res = connector_service.test_connector_connection(db, c["id"])
            self.assertIn(res["status"], ["CONNECTED", "FAILED"])
            self.assertIsNotNone(res["tested_at"])

            updated_c = connector_service.get_connector_by_id(db, c["id"])
            self.assertEqual(updated_c["connection_status"], res["status"])
            self.assertIsNotNone(updated_c["last_tested_at"])

if __name__ == "__main__":
    unittest.main()
