"""
Integration tests for Database Persistence Layer and Real Health Probe
"""

import unittest
from shared.database import initialize_database
from shared.health import get_system_health, check_database_health
from shared.db.session import get_engine

class TestDatabasePersistence(unittest.TestCase):
    def setUp(self):
        initialize_database()

    def test_database_initialization(self):
        engine = get_engine()
        self.assertIsNotNone(engine)

    def test_database_health_check(self):
        res = check_database_health()
        self.assertEqual(res["status"], "healthy")
        self.assertIn("latency_ms", res)
        self.assertIsInstance(res["latency_ms"], int)

    def test_system_health_aggregate(self):
        system_res = get_system_health("req-db-test-001")
        self.assertTrue(system_res["success"])
        self.assertEqual(system_res["data"]["components"]["database"], "healthy")
        self.assertIn("database_details", system_res["data"])

if __name__ == "__main__":
    unittest.main()
