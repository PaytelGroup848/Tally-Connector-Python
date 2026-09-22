"""
Unit tests for Local Database Queue Service (queue_service.py) & sync_queue table schema.
"""

import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.db.base import Base
from shared.db.models.sync import SyncQueue
from apps.backend.services.queue_service import QueueService
from shared.cloud_client import CloudClientError

class TestQueueServiceUnit(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()
        self.mock_cloud_client = MagicMock()
        self.service = QueueService(cloud_client=self.mock_cloud_client, max_retries=3)

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_01_enqueue_payload(self):
        masters_payload = {"masters": [{"name": "Sales Account"}, {"name": "HDFC Bank"}]}
        item = self.service.enqueue_payload(
            db_session=self.session,
            payload_type="MASTERS",
            payload=masters_payload,
            company_identifier="COMP-001",
        )

        self.assertIsNotNone(item.id)
        self.assertEqual(item.payload_type, "MASTERS")
        self.assertEqual(item.status, "PENDING")
        self.assertEqual(item.retry_count, 0)
        self.assertIsNone(item.error_msg)
        self.assertIn("Sales Account", item.payload_json)

    def test_02_process_queue_batch_success(self):
        vouchers_payload = {"vouchers": [{"voucher_number": "INV-101", "amount": 2500.0}]}
        item = self.service.enqueue_payload(
            db_session=self.session,
            payload_type="VOUCHERS",
            payload=vouchers_payload,
        )

        self.mock_cloud_client.sync_vouchers.return_value = {"synced": 1}

        res = self.service.process_queue_batch(
            db_session=self.session, cloud_client=self.mock_cloud_client, batch_size=10
        )

        self.assertEqual(res["total"], 1)
        self.assertEqual(res["synced"], 1)
        self.assertEqual(res["failed"], 0)

        refreshed_item = self.session.get(SyncQueue, item.id)
        self.assertEqual(refreshed_item.status, "SYNCED")
        self.assertIsNone(refreshed_item.error_msg)
        self.mock_cloud_client.sync_vouchers.assert_called_once()

    def test_03_process_queue_batch_retry_on_network_failure(self):
        item = self.service.enqueue_payload(
            db_session=self.session,
            payload_type="MASTERS",
            payload={"masters": [{"name": "Test Ledger"}]},
        )

        self.mock_cloud_client.sync_masters.side_effect = CloudClientError("Cloud Server Timeout")

        res = self.service.process_queue_batch(
            db_session=self.session, cloud_client=self.mock_cloud_client, max_retries=3
        )

        self.assertEqual(res["total"], 1)
        self.assertEqual(res["synced"], 0)
        self.assertEqual(res["failed"], 1)

        refreshed_item = self.session.get(SyncQueue, item.id)
        self.assertEqual(refreshed_item.retry_count, 1)
        self.assertEqual(refreshed_item.status, "FAILED")
        self.assertIn("Cloud Server Timeout", refreshed_item.error_msg)

    def test_04_max_retries_exceeded_critical_alert(self):
        item = self.service.enqueue_payload(
            db_session=self.session,
            payload_type="VOUCHERS",
            payload={"vouchers": [{"voucher_number": "INV-999"}]},
        )
        item.retry_count = 2
        self.session.commit()

        self.mock_cloud_client.sync_vouchers.side_effect = CloudClientError("Permanent Server Error")

        with patch("apps.backend.services.queue_service.logger") as mock_logger:
            res = self.service.process_queue_batch(
                db_session=self.session, cloud_client=self.mock_cloud_client, max_retries=3
            )

            self.assertEqual(res["failed"], 1)
            refreshed_item = self.session.get(SyncQueue, item.id)
            self.assertEqual(refreshed_item.retry_count, 3)
            self.assertEqual(refreshed_item.status, "FAILED")

            mock_logger.error.assert_called()
            log_args = mock_logger.error.call_args[0][0]
            self.assertIn("CRITICAL ALERT", log_args)
            self.assertIn("exceeded max retries", log_args)

if __name__ == "__main__":
    unittest.main()
