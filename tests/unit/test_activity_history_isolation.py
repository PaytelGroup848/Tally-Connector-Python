import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from shared.repositories.activity_history_repository import ActivityHistoryRepository

class DummyCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def _match_doc(self, d, f):
        if not f:
            return True
        if "$and" in f:
            return all(self._match_doc(d, c) for c in f["$and"])
        if "$or" in f:
            return any(self._match_doc(d, c) for c in f["$or"])
        for k, v in f.items():
            if isinstance(v, dict) and "$exists" in v:
                exists = k in d and d[k] is not None
                if exists != v["$exists"]:
                    return False
            elif d.get(k) != v:
                return False
        return True

    def find(self, filter_dict, projection=None):
        class Cursor:
            def __init__(self, data):
                self._data = list(data)

            def sort(self, field, direction):
                return self

            def limit(self, n):
                return self._data[:n]

        matched = [d for d in self.docs if self._match_doc(d, filter_dict)]
        return Cursor(matched)

    def delete_many(self, filter_dict):
        self.docs = [d for d in self.docs if not self._match_doc(d, filter_dict)]


@pytest.fixture
def temp_history_repo(tmp_path):
    repo = ActivityHistoryRepository()
    test_file = tmp_path / "test_history.json"
    with patch("shared.repositories.activity_history_repository.LOCAL_HISTORY_FILE", test_file):
        yield repo, test_file


def test_record_activity_attaches_tenant_metadata(temp_history_repo):
    repo, test_file = temp_history_repo
    dummy_col = DummyCollection()

    with patch("shared.db.mongo_client.get_collection", return_value=dummy_col):
        repo.record_activity({
            "command_id": "cmd_001",
            "voucher_type": "Sales Bill",
            "party": "Test Party",
            "amount": 5000.0,
            "company": "Company A",
            "organization_id": "org_111",
            "user_email": "user_a@test.com",
            "device_id": "dev_a"
        })

    assert len(dummy_col.docs) == 1
    doc = dummy_col.docs[0]
    assert doc["organization_id"] == "org_111"
    assert doc["user_email"] == "user_a@test.com"
    assert doc["device_id"] == "dev_a"
    assert doc["party"] == "Test Party"


def test_get_recent_activities_strictly_isolated(temp_history_repo):
    repo, test_file = temp_history_repo
    dummy_col = DummyCollection()

    with patch("shared.db.mongo_client.get_collection", return_value=dummy_col):
        # User A activity
        repo.record_activity({
            "command_id": "cmd_a",
            "party": "Party Alpha",
            "organization_id": "org_alpha",
            "user_email": "alpha@example.com"
        })
        # User B activity
        repo.record_activity({
            "command_id": "cmd_b",
            "party": "Party Beta",
            "organization_id": "org_beta",
            "user_email": "beta@example.com"
        })

        # Fetch as User A
        res_a = repo.get_recent_activities(organization_id="org_alpha", user_email="alpha@example.com")
        assert len(res_a) == 1
        assert res_a[0]["party"] == "Party Alpha"

        # Fetch as User B
        res_b = repo.get_recent_activities(organization_id="org_beta", user_email="beta@example.com")
        assert len(res_b) == 1
        assert res_b[0]["party"] == "Party Beta"


def test_clear_activities_only_deletes_own_records(temp_history_repo):
    repo, test_file = temp_history_repo
    dummy_col = DummyCollection()

    with patch("shared.db.mongo_client.get_collection", return_value=dummy_col):
        repo.record_activity({
            "command_id": "cmd_1",
            "party": "Party Alpha",
            "organization_id": "org_alpha",
            "user_email": "alpha@example.com"
        })
        repo.record_activity({
            "command_id": "cmd_2",
            "party": "Party Beta",
            "organization_id": "org_beta",
            "user_email": "beta@example.com"
        })

        # Clear ONLY User A
        repo.clear_activities(organization_id="org_alpha", user_email="alpha@example.com")

        # Beta must still exist in MongoDB!
        assert len(dummy_col.docs) == 1
        assert dummy_col.docs[0]["party"] == "Party Beta"

        # Local cache must also keep Beta
        with open(test_file, "r") as f:
            local_items = json.load(f)
        assert len(local_items) == 1
        assert local_items[0]["party"] == "Party Beta"


def test_clear_activities_guards_against_empty_params(temp_history_repo):
    repo, test_file = temp_history_repo
    dummy_col = DummyCollection()

    with patch("shared.db.mongo_client.get_collection", return_value=dummy_col), \
         patch("shared.config.get_settings") as mock_settings:
        mock_settings.return_value.user_organization_id = ""
        mock_settings.return_value.organization_id = ""
        mock_settings.return_value.user_email = ""

        dummy_col.docs.append({"command_id": "cmd_keep", "party": "Party Keep"})

        # Calling clear_activities with empty org/email must NOT wipe MongoDB
        repo.clear_activities(organization_id="", user_email="")
        assert len(dummy_col.docs) == 1

