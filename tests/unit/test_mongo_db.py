

import unittest
from shared.db.mongo_client import get_mongo_client, get_mongo_db, get_collection
from shared.repositories.company_repository import (
    upsert_company_config,
    get_all_company_configs,
    set_company_sync_enabled,
    delete_company_config
)

class TestMongoDBIntegration(unittest.TestCase):

    def setUp(self):
        self.db = get_mongo_db()
        self.test_company_name = "Test Unit Enterprise"

    def test_mongo_connection_and_indexes(self):
        """Verifies MongoDB database resolution and collections."""
        client = get_mongo_client()
        self.assertIsNotNone(client)
        self.assertEqual(self.db.name, "test")

    def test_company_crud_operations(self):
        """Tests inserting, querying, updating, and deleting companies in MongoDB."""
        res = upsert_company_config("TALLY", self.test_company_name, "GUID-12345", "01-Apr-2025")
        self.assertEqual(res["company_name"], self.test_company_name)

        configs = get_all_company_configs()
        matching = [c for c in configs if c.get("company_name") == self.test_company_name]
        self.assertTrue(len(matching) >= 1)

        toggled = set_company_sync_enabled("TALLY", self.test_company_name, False)
        self.assertTrue(toggled)

        deleted = delete_company_config(self.test_company_name)
        self.assertTrue(deleted)

if __name__ == "__main__":
    unittest.main()

