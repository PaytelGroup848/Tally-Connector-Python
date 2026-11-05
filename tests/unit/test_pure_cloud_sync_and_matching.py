import pytest
from unittest.mock import MagicMock, patch
from apps.desktop_app.ui.threads.sync_worker import find_matching_tally_company, BackgroundSyncWorker
from apps.desktop_app.ui.threads.sync_handlers.cloud_push_syncer import push_cloud_sync, validate_batch_response
from shared.config import get_settings


class TestPureCloudSyncAndMatching:

    def test_01_direct_mongo_sync_enabled_is_false(self):
        """Verifies that direct_mongo_sync_enabled is strictly False by default."""
        settings = get_settings()
        assert settings.direct_mongo_sync_enabled is False

    def test_02_company_name_matching_exact(self):
        """Verifies exact case-insensitive trimmed match."""
        open_companies = [
            {"name": "Working  Data", "guid": "guid-working-data"},
            {"name": "Other Company", "guid": "guid-other"}
        ]
        matched, err = find_matching_tally_company("Working  Data", open_companies)
        assert err is None
        assert matched is not None
        assert matched["name"] == "Working  Data"
        assert matched["guid"] == "guid-working-data"

        # Case-insensitive
        matched2, err2 = find_matching_tally_company("working  data", open_companies)
        assert err2 is None
        assert matched2 is not None
        assert matched2["name"] == "Working  Data"

    def test_03_company_name_matching_whitespace_normalized(self):
        """Verifies whitespace & punctuation tolerant matching selects exact Tally name."""
        # Cloud has space inside parenthesis: 'PayTel Terminal Pvt. Ltd.( Haryana)'
        # Tally has space before parenthesis: 'PayTel Terminal Pvt. Ltd. (Haryana)'
        open_companies = [
            {"name": "PayTel Terminal Pvt. Ltd. (Haryana)", "guid": "guid-paytel-haryana"},
            {"name": "PayTel Financial Technologies Pvt. Ltd.(Delhi)", "guid": "guid-paytel-delhi"}
        ]
        matched, err = find_matching_tally_company("PayTel Terminal Pvt. Ltd.( Haryana)", open_companies)
        assert err is None
        assert matched is not None
        # Must return the exact original name in Tally so Tally XML extraction uses it!
        assert matched["name"] == "PayTel Terminal Pvt. Ltd. (Haryana)"
        assert matched["guid"] == "guid-paytel-haryana"

    def test_04_company_name_matching_ambiguous_fails_safely(self):
        """Verifies that ambiguous multiple matches halt sync with a clear error."""
        open_companies = [
            {"name": "PayTel Terminal Pvt. Ltd. (Haryana)", "guid": "g1"},
            {"name": "PayTel Terminal Pvt. Ltd.(Haryana)", "guid": "g2"}
        ]
        matched, err = find_matching_tally_company("PayTel Terminal Pvt. Ltd.( Haryana)", open_companies)
        assert matched is None
        assert err is not None
        assert "Ambiguous company match" in err
        assert "Multiple open companies in Tally match" in err

    def test_05_company_name_matching_no_match(self):
        """Verifies no match returns None and no crash."""
        open_companies = [{"name": "Different Company", "guid": "g1"}]
        matched, err = find_matching_tally_company("PayTel Terminal Pvt. Ltd.( Haryana)", open_companies)
        assert matched is None
        assert err is None

        # Empty open companies
        matched_empty, err_empty = find_matching_tally_company("Target", [])
        assert matched_empty is None
        assert "No companies are currently open in Tally Prime" in err_empty

    @patch("apps.desktop_app.ui.threads.sync_handlers.cloud_push_syncer.cloud_auth_service")
    def test_06_cloud_push_failed_batch_reporting(self, mock_auth):
        """Verifies that if any batch fails, push_cloud_sync returns False and clear error."""
        mock_auth.access_token = "valid_test_token"
        mock_auth.sync_start.return_value = (True, "Started", {"syncJobId": "job-123"})
        # 1st batch succeeds with valid counts, 2nd batch fails
        mock_auth.sync_batch.side_effect = [
            (True, "OK", {"upserted": 100, "failed": 0}),
            (False, "Payload validation failed", {})
        ]
        mock_auth.sync_complete.return_value = (True, "Completed", {})

        worker = MagicMock()
        worker._is_cancelled = False

        ledgers = [{"name": f"L{i}"} for i in range(150)]  # 2 chunks of 100
        ok, msg = push_cloud_sync(
            worker=worker,
            c_name="Test Company",
            c_guid="test-guid",
            extracted_ledgers=ledgers,
            extracted_stock_items=[],
            extracted_vouchers=[],
            last_alter_id=100,
            base_pct=0,
            idx=1,
            total_companies=1,
            is_incremental=False
        )

        assert ok is False
        assert "Cloud sync incomplete: 1 batch(es) failed" in msg
        # Verifies sync_complete was called with FAILED status
        mock_auth.sync_complete.assert_called_once()
        complete_call_args = mock_auth.sync_complete.call_args[1]
        assert complete_call_args["status"] == "FAILED"

    @patch("apps.desktop_app.ui.threads.sync_handlers.cloud_push_syncer.cloud_auth_service")
    def test_07_cloud_push_successful_reporting(self, mock_auth):
        """Verifies that when all batches succeed, push_cloud_sync returns True."""
        mock_auth.access_token = "valid_test_token"
        mock_auth.sync_start.return_value = (True, "Started", {"syncJobId": "job-123"})
        mock_auth.sync_batch.return_value = (True, "OK", {"upserted": 1, "failed": 0})
        mock_auth.sync_complete.return_value = (True, "Completed", {})

        worker = MagicMock()
        worker._is_cancelled = False

        ok, msg = push_cloud_sync(
            worker=worker,
            c_name="Test Company",
            c_guid="test-guid",
            extracted_ledgers=[{"name": "L1"}],
            extracted_stock_items=[],
            extracted_vouchers=[{"voucherNumber": "V1"}],
            last_alter_id=100,
            base_pct=0,
            idx=1,
            total_companies=1,
            is_incremental=False
        )

        assert ok is True
        assert "Successfully pushed" in msg
        complete_call_args = mock_auth.sync_complete.call_args[1]
        assert complete_call_args["status"] == "COMPLETED"

    def test_08_batch_validation_success_counts(self):
        """Verifies HTTP 200, upserted > 0, failed = 0 passes validation."""
        is_valid, count, msg = validate_batch_response(
            ok_b=True,
            msg_b="Batch accepted",
            b_data={"upserted": 25, "failed": 0},
            expected_count=25
        )
        assert is_valid is True
        assert count == 25
        assert "Batch accepted" in msg

        # Also support nested payload: {"data": {"upserted": 50, "failed": 0}}
        is_valid_n, count_n, _ = validate_batch_response(
            ok_b=True,
            msg_b="OK",
            b_data={"data": {"upserted": 50, "failed": 0}},
            expected_count=50
        )
        assert is_valid_n is True
        assert count_n == 50

    def test_09_batch_validation_partial_failure(self):
        """Verifies HTTP 200 with failed > 0 is treated as a batch failure."""
        is_valid, count, err = validate_batch_response(
            ok_b=True,
            msg_b="OK",
            b_data={"upserted": 20, "failed": 5, "errors": ["Party GSTIN format invalid"]},
            expected_count=25
        )
        assert is_valid is False
        assert count == 20
        assert "Batch reported 5 failed record(s)" in err
        assert "Party GSTIN format invalid" in err

    def test_10_batch_validation_missing_or_invalid_counts(self):
        """Verifies missing or invalid counts are safely rejected without assuming 0."""
        # Missing 'failed' field
        is_valid1, _, err1 = validate_batch_response(True, "OK", {"upserted": 10}, expected_count=10)
        assert is_valid1 is False
        assert "missing required count field(s): failed" in err1

        # Missing 'upserted' field
        is_valid2, _, err2 = validate_batch_response(True, "OK", {"failed": 0}, expected_count=10)
        assert is_valid2 is False
        assert "missing required count field(s): upserted" in err2

        # Empty dict (missing both)
        is_valid3, _, err3 = validate_batch_response(True, "OK", {}, expected_count=10)
        assert is_valid3 is False
        assert "missing required count field(s): upserted, failed" in err3

        # Invalid non-numeric counts
        is_valid4, _, err4 = validate_batch_response(True, "OK", {"upserted": "bad", "failed": 0}, expected_count=10)
        assert is_valid4 is False
        assert "Invalid count types" in err4

        # Negative counts
        is_valid5, _, err5 = validate_batch_response(True, "OK", {"upserted": 10, "failed": -1}, expected_count=10)
        assert is_valid5 is False
        assert "Invalid negative count" in err5

        # Contradictory: 10 items sent but 0 upserted and 0 failed
        is_valid6, _, err6 = validate_batch_response(True, "OK", {"upserted": 0, "failed": 0}, expected_count=10)
        assert is_valid6 is False
        assert "Contradictory batch response: 10 records sent but 0 upserted and 0 failed" in err6

    def test_11_batch_validation_http_or_network_error(self):
        """Verifies HTTP / network errors are caught immediately."""
        is_valid, count, err = validate_batch_response(
            ok_b=False,
            msg_b="HTTP 502 Bad Gateway",
            b_data={},
            expected_count=10
        )
        assert is_valid is False
        assert count == 0
        assert "HTTP 502 Bad Gateway" in err

    @patch("apps.desktop_app.ui.threads.sync_handlers.cloud_push_syncer.cloud_auth_service")
    def test_12_cloud_push_partial_batch_failure_marks_sync_failed(self, mock_auth):
        """Verifies end-to-end push_cloud_sync returns False and marks session FAILED on partial batch failure."""
        mock_auth.access_token = "valid_test_token"
        mock_auth.sync_start.return_value = (True, "Started", {"syncJobId": "job-partial-1"})
        # 1st batch reports 2 items failed out of 10
        mock_auth.sync_batch.return_value = (True, "OK", {"upserted": 8, "failed": 2})
        mock_auth.sync_complete.return_value = (True, "Completed", {})

        worker = MagicMock()
        worker._is_cancelled = False

        vouchers = [{"voucherNumber": f"V{i}"} for i in range(10)]
        ok, msg = push_cloud_sync(
            worker=worker,
            c_name="Test Company",
            c_guid="test-guid",
            extracted_ledgers=[],
            extracted_stock_items=[],
            extracted_vouchers=vouchers,
            last_alter_id=500,
            base_pct=0,
            idx=1,
            total_companies=1,
            is_incremental=False
        )

        assert ok is False
        assert "Cloud sync incomplete: 1 batch(es) failed" in msg
        assert "Batch reported 2 failed record(s)" in msg
        # Verifies sync_complete was explicitly sent status FAILED
        mock_auth.sync_complete.assert_called_once()
        assert mock_auth.sync_complete.call_args[1]["status"] == "FAILED"

    def test_13_partial_failure_leaves_checkpoint_unchanged(self):
        """Verifies that when push_cloud_sync returns False due to partial failure, sync worker does NOT update checkpoints."""
        worker = BackgroundSyncWorker(source="TALLY", is_full_sync=False)
        worker.progress_changed = MagicMock()
        worker.company_synced = MagicMock()
        worker._get_open_tally_companies = MagicMock(return_value=[{"name": "Test Co", "guid": "guid-123"}])
        worker._sync_groups = MagicMock()
        worker._sync_godowns = MagicMock()
        worker._sync_units = MagicMock()
        worker._sync_stock_groups = MagicMock()
        worker._sync_voucher_types = MagicMock()
        worker._sync_ledgers = MagicMock(return_value=([], 150))
        worker._sync_stock_items = MagicMock(return_value=([], 0))
        worker._sync_vouchers = MagicMock(return_value=([{"voucherNumber": "V10"}], 250))
        # Push fails due to partial batch failure
        worker._push_cloud_sync = MagicMock(return_value=(False, "Cloud sync incomplete: 1 batch(es) failed (Batch reported 1 failed record(s))"))
        worker._reconcile_pending_commands = MagicMock()
        worker._resolve_ids = MagicMock(return_value=(None, None))

        with patch("apps.desktop_app.ui.threads.sync_worker.get_collection") as mock_gc:
            mock_col = MagicMock()
            # Current checkpoint is 150
            mock_col.find_one.return_value = {"company_name": "Test Co", "last_voucher_alter_id": 150}
            mock_gc.return_value = mock_col

            ok, err = worker._sync_single_company(
                {"company_name": "Test Co", "company_guid": "guid-123"},
                1, 1, 9000, [{"name": "Test Co", "guid": "guid-123"}]
            )

            # Sync must fail
            assert ok is False
            assert "Cloud sync incomplete" in err
            # Checkpoint must NOT be updated (update_one must never be called)
            assert mock_col.update_one.called is False



    def test_14_local_checkpoint_read_write(self, tmp_path, monkeypatch):
        """Verifies local checkpoint get/set persistence without MongoDB."""
        from shared.cloud.helpers import set_local_checkpoint, get_local_checkpoint
        import shared.cloud.helpers as helpers

        fake_file = tmp_path / "sync_checkpoints.json"
        monkeypatch.setattr(helpers, "SYNC_CHECKPOINTS_FILE", fake_file)

        set_local_checkpoint(
            company_key="650000000000000000000001",
            last_alter_id=450,
            last_voucher_alter_id=450,
            status="SYNCED",
            stats={"ledgers": 12, "vouchers": 45, "items": 5},
            company_name="Alpha Traders (Delhi)",
            cloud_company_id="650000000000000000000001"
        )

        # 1. Lookup by ObjectId
        cp1 = get_local_checkpoint("650000000000000000000001")
        assert cp1 is not None
        assert cp1["last_alter_id"] == 450
        assert cp1["last_voucher_alter_id"] == 450
        assert cp1["status"] == "SYNCED"
        assert cp1["stats"]["vouchers"] == 45

        # 2. Lookup by Company Name
        cp2 = get_local_checkpoint("Alpha Traders (Delhi)")
        assert cp2 is not None
        assert cp2["last_alter_id"] == 450

        # 3. Lookup by whitespace-normalized name
        cp3 = get_local_checkpoint("Alpha Traders( Delhi)")
        assert cp3 is not None
        assert cp3["last_alter_id"] == 450

    @patch("shared.auth.cloud_auth_service.cloud_auth_service")
    def test_15_get_all_company_configs_pure_cloud(self, mock_auth):
        """Verifies get_all_company_configs loads canonical companies from Cloud API in pure cloud mode."""
        from shared.repositories.company_repository import get_all_company_configs

        mock_auth.is_authenticated = True
        mock_auth.get_cloud_companies.return_value = (True, [
            {
                "id": "670000000000000000000001",
                "tallyCompanyName": "Beta Global Inc. (Haryana)",
                "tallyCompanyGuid": "guid-beta",
                "isSyncEnabled": True,
                "status": "CONNECTED"
            }
        ])

        with patch("shared.repositories.company_repository.get_collection") as mock_gc:
            configs = get_all_company_configs()
            assert len(configs) == 1
            assert configs[0]["company_name"] == "Beta Global Inc. (Haryana)"
            assert configs[0]["cloud_company_id"] == "670000000000000000000001"
            # MongoDB collection must NEVER be queried in pure cloud mode!
            mock_gc.assert_not_called()

    def test_16_cloud_sync_client_normalized_name_matching(self):
        """Verifies CloudSyncClient.sync_start matches company names despite whitespace differences."""
        from shared.cloud.cloud_sync_client import CloudSyncClient

        mock_auth = MagicMock()
        mock_auth.base_url = "https://connector.cloudata.in/api/connector"
        mock_auth.access_token = "valid_token"
        mock_auth._device_id = "test-device"
        mock_auth.get_cloud_companies.return_value = (True, [
            {
                "id": "67bc954f92d4b9fbb0ad70d8",
                "tallyCompanyName": "PayTel Terminal Pvt. Ltd. (Haryana)",
                "companyGuid": "guid-123"
            }
        ])
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"success": True, "data": {"syncJobId": "job-abc"}}
        mock_res.text = '{"success": true}'
        mock_client.post.return_value = mock_res
        mock_auth._get_client.return_value = mock_client

        sync_client = CloudSyncClient(mock_auth)

        # Notice extra whitespace in passed company name: 'PayTel Terminal Pvt. Ltd.( Haryana)'
        ok, msg, data = sync_client.sync_start(
            company_name="PayTel Terminal Pvt. Ltd.( Haryana)",
            company_guid="guid-123",
            sync_type="INCREMENTAL",
            total_records=10
        )

        assert ok is True
        assert data.get("syncJobId") == "job-abc"
        # Verifies the request payload used the canonical 24-character ObjectId
        post_kwargs = mock_client.post.call_args[1]
        assert post_kwargs["json"]["companyId"] == "67bc954f92d4b9fbb0ad70d8"

    def test_17_cloud_sync_client_passes_company_id_directly(self):
        """Verifies CloudSyncClient.sync_start directly uses company_id when passed."""
        from shared.cloud.cloud_sync_client import CloudSyncClient

        mock_auth = MagicMock()
        mock_auth.base_url = "https://connector.cloudata.in/api/connector"
        mock_auth.access_token = "valid_token"
        mock_auth._device_id = "test-device"
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"success": True, "data": {"syncJobId": "job-direct"}}
        mock_res.text = '{"success": true}'
        mock_client.post.return_value = mock_res
        mock_auth._get_client.return_value = mock_client

        sync_client = CloudSyncClient(mock_auth)

        ok, msg, data = sync_client.sync_start(
            company_name="Any Arbitrary Company",
            company_id="67bc954f92d4b9fbb0ad7099",
            sync_type="FULL",
            total_records=5
        )

        assert ok is True
        # Did not need get_cloud_companies because company_id was given
        mock_auth.get_cloud_companies.assert_not_called()
        post_kwargs = mock_client.post.call_args[1]
        assert post_kwargs["json"]["companyId"] == "67bc954f92d4b9fbb0ad7099"


    def test_18_voucher_xml_builder_omits_invalid_childof_tags(self):
        """Verifies build_collection_xml for Voucher never contains invalid CHILDOF/BELONGSTO tags."""
        from apps.backend.adapters.tally.request_builder import build_collection_xml, build_daybook_export_xml

        v_xml = build_collection_xml(
            collection_type="Voucher",
            fetch_fields=["DATE", "VOUCHERNUMBER", "AMOUNT"],
            company_name="Madan Pvt Ltd",
            from_alter_id=None
        )

        assert "<CHILDOF>" not in v_xml
        assert "<BELONGSTO>" not in v_xml
        assert "<TYPE>Voucher</TYPE>" in v_xml
        assert "<SVCURRENTCOMPANY>Madan Pvt Ltd</SVCURRENTCOMPANY>" in v_xml
        assert "<SVFROMDATE TYPE=\"Date\">20000101</SVFROMDATE>" in v_xml
        assert "<SVTODATE TYPE=\"Date\">20991231</SVTODATE>" in v_xml

        # Also verify native Day Book export XML
        db_xml = build_daybook_export_xml("Madan Pvt Ltd", "20000101", "20991231")
        assert "<REPORTNAME>Day Book</REPORTNAME>" in db_xml
        assert "<SVCURRENTCOMPANY>Madan Pvt Ltd</SVCURRENTCOMPANY>" in db_xml

    def test_19_voucher_sync_batch_enrichment(self):
        """Verifies CloudSyncClient.sync_batch serializes rich invoice and GSTIN fields for VOUCHER entity."""
        from shared.cloud.cloud_sync_client import CloudSyncClient

        mock_auth = MagicMock()
        mock_auth.base_url = "https://connector.cloudata.in/api/connector"
        mock_auth.access_token = "valid_token"
        mock_auth._device_id = "test-device"
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"success": True, "data": {"upserted": 1, "failed": 0}}
        mock_res.text = '{"success": true}'
        mock_client.post.return_value = mock_res
        mock_auth._get_client.return_value = mock_client

        sync_client = CloudSyncClient(mock_auth)

        voucher_item = {
            "voucherId": "vch-guid-101",
            "voucherNumber": "INV-2026-001",
            "voucherType": "Sales",
            "date": "2026-10-28",
            "amount": 15000.0,
            "partyLedger": "Acme Corp",
            "partyGstin": "07AAAAA0000A1Z5",
            "items": [{"itemName": "Widget", "quantity": 10, "rate": 1500.0}],
            "lines": [{"ledgerName": "Sales Account", "amount": 15000.0}]
        }

        ok, msg, data = sync_client.sync_batch(
            sync_id="job-vch-1",
            company_name="Madan Pvt Ltd",
            entity_type="VOUCHER",
            items=[voucher_item],
            batch_number=1,
            is_last_batch=True
        )

        assert ok is True
        post_kwargs = mock_client.post.call_args[1]
        sent_body = post_kwargs["json"]
        assert sent_body["entityType"] == "VOUCHER"
        rec = sent_body["records"][0]
        assert rec["voucherNumber"] == "INV-2026-001"
        assert rec["invoiceNumber"] == "INV-2026-001"
        assert rec["voucherType"] == "Sales"
        assert rec["invoiceType"] == "Sales"
        assert rec["date"] == "2026-10-28"
        assert rec["invoiceDate"] == "2026-10-28"
        assert rec["amount"] == 15000.0
        assert rec["partyGstin"] == "07AAAAA0000A1Z5"
        assert rec["gstin"] == "07AAAAA0000A1Z5"
        assert len(rec["items"]) == 1
        assert len(rec["lines"]) == 1

    def test_20_no_subscription_maps_to_registered_with_different_email(self):
        """Verifies 'No subscription found' from cloud is mapped to 'This company is already registered with a different email address.'"""
        from apps.desktop_app.ui.threads.sync_handlers.cloud_push_syncer import push_cloud_sync
        from shared.auth.cloud_auth_service import cloud_auth_service

        mock_worker = MagicMock()
        mock_worker._is_cancelled = False

        with patch.object(cloud_auth_service, "access_token", "valid-token"):
            with patch.object(cloud_auth_service, "sync_start", return_value=(False, "No subscription found", {})):
                ok, err = push_cloud_sync(
                    worker=mock_worker,
                    c_name="Apna Ganesh Pvt Ltd",
                    c_guid="guid-123",
                    extracted_ledgers=[],
                    extracted_stock_items=[],
                    extracted_vouchers=[],
                    last_alter_id=0,
                    base_pct=0,
                    idx=1,
                    total_companies=1,
                    is_incremental=False
                )
                assert ok is False
                assert err == "This company is already registered with a different email address."

        # Verify _extract_error_message conversion
        mock_res = MagicMock()
        mock_res.status_code = 400
        extracted = cloud_auth_service._extract_error_message(mock_res, {"message": "No subscription found"}, "Default error")
        assert extracted == "This company is already registered with a different email address."

    def test_21_cloud_batch_payload_initial_and_incremental(self):
        """Verifies CloudSyncClient.sync_batch sends the required /api/companies/:id/sync/batch URL
        and INITIAL (with startDate, endDate, isFullReplace=True) vs INCREMENTAL (isFullReplace=False) payload format."""
        from shared.cloud.cloud_sync_client import CloudSyncClient

        mock_auth = MagicMock()
        mock_auth.base_url = "https://connector.cloudata.in/api/connector"
        mock_auth.access_token = "valid_token"
        mock_auth._device_id = "test-device"
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"success": True, "data": {"upserted": 1, "failed": 0}}
        mock_res.text = '{"success": true}'
        mock_client.post.return_value = mock_res
        mock_auth._get_client.return_value = mock_client

        sync_client = CloudSyncClient(mock_auth)

        voucher_item = {
            "voucherId": "vch-4f3f4b54",
            "tallyExternalId": "vch-4f3f4b54",
            "voucherNumber": "14",
            "voucherType": "Sales",
            "date": "2026-10-12",
            "amount": 116.82,
            "partyLedger": "HDFC BANK-9593",
            "customerName": "HDFC BANK-9593",
            "lines": [],
            "items": []
        }

        # 1. Test INITIAL sync
        ok, msg, data = sync_client.sync_batch(
            sync_id="6ae49663fa5e92fc56700ccc",
            company_name="Test Company",
            entity_type="VOUCHER",
            items=[voucher_item],
            batch_number=1,
            is_last_batch=True,
            company_id="6ae494a2170b689d53e04033",
            sync_type="INITIAL",
            is_full_replace=True,
            start_date="2025-03-01",
            end_date="2026-03-01"
        )
        assert ok is True
        call_args = mock_client.post.call_args
        target_url = call_args[0][0]
        sent_body = call_args[1]["json"]

        # Check URL
        assert target_url == "https://connector.cloudata.in/api/connector/6ae494a2170b689d53e04033/sync/batch"
        # Check INITIAL Payload fields
        assert sent_body["syncJobId"] == "6ae49663fa5e92fc56700ccc"
        assert sent_body["companyId"] == "6ae494a2170b689d53e04033"
        assert sent_body["entityType"] == "VOUCHER"
        assert sent_body["syncType"] == "INITIAL"
        assert sent_body["isFullReplace"] is True
        assert sent_body["startDate"] == "2025-03-01"
        assert sent_body["endDate"] == "2026-03-01"
        assert len(sent_body["records"]) == 1
        rec = sent_body["records"][0]
        assert rec["voucherId"] == "vch-4f3f4b54"
        assert rec["voucherNumber"] == "14"
        assert rec["amount"] == 116.82

        # 2. Test INCREMENTAL sync
        ok2, msg2, data2 = sync_client.sync_batch(
            sync_id="6ae49663fa5e92fc56700ccc",
            company_name="Test Company",
            entity_type="VOUCHER",
            items=[voucher_item],
            batch_number=1,
            is_last_batch=True,
            company_id="6ae494a2170b689d53e04033",
            sync_type="INCREMENTAL",
            is_full_replace=False
        )
        assert ok2 is True
        call_args2 = mock_client.post.call_args
        target_url2 = call_args2[0][0]
        sent_body2 = call_args2[1]["json"]

        assert target_url2 == "https://connector.cloudata.in/api/connector/6ae494a2170b689d53e04033/sync/batch"
        assert sent_body2["syncJobId"] == "6ae49663fa5e92fc56700ccc"
        assert sent_body2["companyId"] == "6ae494a2170b689d53e04033"
        assert sent_body2["entityType"] == "VOUCHER"
        assert sent_body2["syncType"] == "INCREMENTAL"
        assert sent_body2["isFullReplace"] is False
        assert "startDate" not in sent_body2
        assert "endDate" not in sent_body2

