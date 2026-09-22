"""
Unit tests for Database Configuration & Engine Management
"""

import os
import unittest
from shared.config import Settings, reset_settings
from shared.db.session import get_engine, reset_engine

class TestDatabaseConfig(unittest.TestCase):
    def setUp(self):
        reset_settings()
        reset_engine()
        self.original_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_settings()
        reset_engine()

    def test_default_sqlite_url(self):
        settings = Settings.load_from_env()
        url = settings.effective_database_url
        self.assertTrue(url.startswith("sqlite:///"))
        self.assertIn("ctrlbooks.db", url)

    def test_custom_database_url(self):
        os.environ["DATABASE_URL"] = "postgresql://user:secretpass@localhost:5432/testdb"
        settings = Settings.load_from_env()
        self.assertEqual(settings.effective_database_url, "postgresql://user:secretpass@localhost:5432/testdb")
        masked = settings.get_masked_dict()
        self.assertEqual(masked["database_url"], "****")

    def test_in_memory_engine_creation(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        settings = Settings.load_from_env()
        engine = get_engine()
        self.assertEqual(str(engine.url), "sqlite:///:memory:")

if __name__ == "__main__":
    unittest.main()
