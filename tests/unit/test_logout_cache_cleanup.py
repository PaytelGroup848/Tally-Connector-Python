import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from shared.auth.cloud_auth_service import cloud_auth_service, AUTH_SESSION_FILE
from shared.cloud.helpers import (
    SYNC_CHECKPOINTS_FILE,
    set_local_checkpoint,
    get_all_local_checkpoints,
    clear_all_local_checkpoints,
    _get_writable_data_file,
)
from apps.desktop_app.ui.threads.company_fetch_worker import _FETCHED_COMPANIES_CACHE
from apps.backend.adapters.tally.response_parser import _ITEM_MASTER_LOOKUP_CACHE


def test_fetched_companies_cache_export():
    """Verify _FETCHED_COMPANIES_CACHE is properly defined and can be imported."""
    assert isinstance(_FETCHED_COMPANIES_CACHE, dict)
    _FETCHED_COMPANIES_CACHE["test_company"] = {"name": "Test"}
    assert len(_FETCHED_COMPANIES_CACHE) == 1
    _FETCHED_COMPANIES_CACHE.clear()
    assert len(_FETCHED_COMPANIES_CACHE) == 0


def test_complete_logout_cache_and_checkpoint_wipe(tmp_path):
    """Verify that logout() clears cookies, session, profile, pending vouchers, checkpoints, and memory caches."""
    # Setup dummy data in all cache locations
    cloud_auth_service.access_token = "dummy_token"
    cloud_auth_service.refresh_token_val = "dummy_refresh"
    cloud_auth_service.current_user = {"email": "test@ctrlbooks.com", "organizationId": "org_123"}

    # In-memory caches
    _FETCHED_COMPANIES_CACHE["cached_comp"] = {"name": "Cached Company"}
    _ITEM_MASTER_LOOKUP_CACHE[("", "item_1")] = {"guid": "guid-123"}

    # Disk caches
    for fname in ("auth_session.json", "profile.json", "pending_vouchers.json", "sync_checkpoints.json"):
        p_data = Path("data") / fname
        p_data.parent.mkdir(parents=True, exist_ok=True)
        with open(p_data, "w", encoding="utf-8") as f:
            f.write(json.dumps({"test": "data"}))

        p_writable = _get_writable_data_file(fname)
        p_writable.parent.mkdir(parents=True, exist_ok=True)
        with open(p_writable, "w", encoding="utf-8") as f:
            f.write(json.dumps({"test": "data"}))

    assert len(_FETCHED_COMPANIES_CACHE) > 0
    assert len(_ITEM_MASTER_LOOKUP_CACHE) > 0

    # Perform logout
    ok, msg = cloud_auth_service.logout()
    assert ok is True
    assert cloud_auth_service.access_token is None
    assert cloud_auth_service.refresh_token_val is None
    assert cloud_auth_service.current_user == {}

    # Verify memory caches wiped
    assert len(_FETCHED_COMPANIES_CACHE) == 0
    assert len(_ITEM_MASTER_LOOKUP_CACHE) == 0

    # Verify disk files removed
    for fname in ("auth_session.json", "profile.json", "pending_vouchers.json", "sync_checkpoints.json"):
        p_data = Path("data") / fname
        assert not p_data.exists(), f"File {p_data} should have been unlinked on logout"
        p_writable = _get_writable_data_file(fname)
        assert not p_writable.exists(), f"File {p_writable} should have been unlinked on logout"
