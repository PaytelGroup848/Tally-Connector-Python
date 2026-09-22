"""
CtrlBooks - Module 10 Integration Tests
---------------------------------------------------
Integration tests for Data Extraction REST API endpoints, read-only preview mode,
concurrency protection, extraction history, and RBAC permissions.
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.db.session import get_db_session
from shared.db.models.user import User
from shared.db.models.connector import Connector
from shared.auth.tokens import create_access_token
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.connector_repo import ConnectorRepository, DataSourceRepository, DestinationRepository
from shared.repositories.mapping_repo import MappingRepository

client = TestClient(app)

MOCK_TALLY_XML = """
<ENVELOPE>
  <BODY>
    <DATA>
      <COLLECTION>
        <LEDGER NAME="Cash">
          <NAME>Cash</NAME>
          <PARENT>Cash-in-Hand</PARENT>
          <CLOSINGBALANCE>5000.0</CLOSINGBALANCE>
          <OPENINGBALANCE>5000.0</OPENINGBALANCE>
          <GUID>guid-cash-100</GUID>
        </LEDGER>
        <STOCKITEM NAME="Stock Item A">
          <NAME>Stock Item A</NAME>
          <PARENT>General</PARENT>
          <GUID>guid-stock-100</GUID>
        </STOCKITEM>
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>
"""

@pytest.fixture(scope="module")
def extraction_test_context():
    """Sets up database test records for connectors, companies, users, roles, and mappings."""
    user_repo = UserRepository()
    role_repo = RoleRepository()
    ds_repo = DataSourceRepository()
    dest_repo = DestinationRepository()
    conn_repo = ConnectorRepository()
    map_repo = MappingRepository()

    with get_db_session() as db:
        admin_role = role_repo.get_by_name(db, "ADMIN")
        if not admin_role:
            admin_role = role_repo.get_by_code(db, "ADMIN")

        admin_user = user_repo.get_by_username(db, "admin_extractor")
        if not admin_user:
            u_admin = User(
                username="admin_extractor",
                full_name="Admin Extractor",
                email="admin_extractor@example.com",
                password_hash=hash_password("Password123!"),
                status="ACTIVE"
            )
            admin_user = user_repo.create(db, u_admin)
            if admin_role:
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
        else:
            admin_user.status = "ACTIVE"
            if admin_role:
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
        db.commit()

        admin_token = create_access_token({"sub": admin_user.id, "username": admin_user.username, "role": "ADMIN"})

        viewer_role = role_repo.get_by_name(db, "VIEWER")
        if not viewer_role:
            viewer_role = role_repo.get_by_code(db, "VIEWER")

        viewer_user = user_repo.get_by_username(db, "viewer_extractor")
        if not viewer_user:
            u_viewer = User(
                username="viewer_extractor",
                full_name="Viewer Extractor",
                email="viewer_extractor@example.com",
                password_hash=hash_password("Password123!"),
                status="ACTIVE"
            )
            viewer_user = user_repo.create(db, u_viewer)
            if viewer_role:
                role_repo.assign_role_to_user(db, viewer_user.id, viewer_role.id)

        viewer_token = create_access_token({"sub": viewer_user.id, "username": viewer_user.username, "role": "VIEWER"})

        ds = ds_repo.create_source(db, "Extract Test Source", "TALLY", {"host": "127.0.0.1", "port": 9000})
        dest = dest_repo.create_destination(db, "Extract Test Dest", "REST_API", {"endpoint": "http://localhost/api"})

        conn = conn_repo.create(db, Connector(
            name="Extract Tally Pipeline",
            connector_type="TALLY",
            description="Integration test pipeline for Module 10",
            source_id=ds.id,
            destination_id=dest.id,
            configuration_json='{"host": "127.0.0.1", "port": 9000, "company_name": "Demo Tally Company Pvt Ltd"}',
            is_active=True,
            connection_status="CONNECTED",
            status="ACTIVE",
            created_by=admin_user.id
        ))

        mapping = map_repo.create_mapping(
            db=db,
            name="Extraction Preview Mapping",
            source_connector_id=conn.id,
            source_company_identifier="Demo Tally Company Pvt Ltd",
            target_connector_id=conn.id,
            target_company_identifier="Demo Tally Target",
            canonical_entity_type="LEDGER",
            description="Mapping for extraction preview integration test",
            status="ACTIVE",
            created_by=admin_user.id
        )
        map_repo.create_field_rule(db, mapping.id, "name", "AccountName", transformation_type="UPPERCASE")
        conn_id = str(conn.id)
        mapping_id = str(mapping.id)

    return {
        "admin_token": admin_token,
        "viewer_token": viewer_token,
        "connector_id": conn_id,
        "company_name": "Demo Tally Company Pvt Ltd",
        "mapping_id": mapping_id
    }

class TestExtractionAPIIntegration:
    def test_01_extract_entity_unauthorized(self, extraction_test_context):
        cid = extraction_test_context["connector_id"]
        res = client.post(f"/api/connectors/{cid}/extract", json={
            "company_identifier": extraction_test_context["company_name"],
            "entity_type": "LEDGER",
            "page_size": 10
        })
        assert res.status_code == 401

    @patch("apps.backend.adapters.tally.tally_client.TallyClient.send_xml_request_async", new_callable=AsyncMock)
    def test_02_extract_entity_canonical_mode(self, mock_tally, extraction_test_context):
        mock_tally.return_value = (True, 200, MOCK_TALLY_XML, None)
        cid = extraction_test_context["connector_id"]
        token = extraction_test_context["admin_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "company_identifier": extraction_test_context["company_name"],
            "entity_type": "LEDGER",
            "page_size": 20
        }
        res = client.post(f"/api/connectors/{cid}/extract", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        ext_data = data.get("data", {})
        assert ext_data.get("connector_id") == cid
        assert ext_data.get("entity_type") == "LEDGER"
        assert ext_data.get("mode") == "CANONICAL"
        assert "run_id" in ext_data
        assert "records" in ext_data

    @patch("apps.backend.adapters.tally.tally_client.TallyClient.send_xml_request_async", new_callable=AsyncMock)
    def test_03_extract_entity_mapped_preview_mode(self, mock_tally, extraction_test_context):
        mock_tally.return_value = (True, 200, MOCK_TALLY_XML, None)
        cid = extraction_test_context["connector_id"]
        token = extraction_test_context["admin_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "company_identifier": extraction_test_context["company_name"],
            "entity_type": "LEDGER",
            "mapping_id": extraction_test_context["mapping_id"],
            "page_size": 10
        }
        res = client.post(f"/api/connectors/{cid}/extract", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        ext_data = data.get("data", {})
        assert ext_data.get("mode") == "MAPPED_PREVIEW"

    @patch("apps.backend.adapters.tally.tally_client.TallyClient.send_xml_request_async", new_callable=AsyncMock)
    def test_04_preview_extraction_endpoint(self, mock_tally, extraction_test_context):
        mock_tally.return_value = (True, 200, MOCK_TALLY_XML, None)
        cid = extraction_test_context["connector_id"]
        token = extraction_test_context["admin_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "company_identifier": extraction_test_context["company_name"],
            "entity_type": "STOCK_ITEM",
            "limit": 5
        }
        res = client.post(f"/api/connectors/{cid}/extract/preview", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        ext_data = data.get("data", {})
        assert ext_data.get("is_preview") is True
        assert "notice" in ext_data

    @patch("apps.backend.adapters.tally.tally_client.TallyClient.send_xml_request_async", new_callable=AsyncMock)
    def test_05_get_single_source_record(self, mock_tally, extraction_test_context):
        mock_tally.return_value = (True, 200, MOCK_TALLY_XML, None)
        cid = extraction_test_context["connector_id"]
        comp = extraction_test_context["company_name"]
        token = extraction_test_context["admin_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get(
            f"/api/connectors/{cid}/extract/LEDGER/Cash?company_identifier={comp}",
            headers=headers
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        rec = data.get("data", {})
        assert rec.get("canonical_entity_type") == "LEDGER"

    def test_06_list_extraction_history(self, extraction_test_context):
        token = extraction_test_context["admin_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get("/api/extractions?page=1&page_size=10", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        history = data.get("data", {})
        assert "items" in history
        assert len(history["items"]) > 0

    def test_07_get_extraction_run_details(self, extraction_test_context):
        token = extraction_test_context["admin_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res_list = client.get("/api/extractions?page=1&page_size=5", headers=headers)
        run_id = res_list.json()["data"]["items"][0]["run_id"]

        res = client.get(f"/api/extractions/{run_id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        run_data = data.get("data", {})
        assert run_data["run_id"] == run_id
        assert "records_returned" in run_data
