"""
Unit tests for Heartbeat & Telemetry System (apps/agent/telemetry.py).
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from apps.agent.telemetry import (
    TelemetryManager,
    update_last_sync_timestamp,
    get_last_sync_timestamp,
)

class TestTelemetryUnit(unittest.TestCase):

    def setUp(self):
        self.mock_cloud_client = MagicMock()
        self.mock_cloud_client.client_id = "test-agent-client-001"
        self.manager = TelemetryManager(cloud_client=self.mock_cloud_client, interval_seconds=1)

    def tearDown(self):
        self.manager.stop_heartbeat_loop()

    def test_01_last_sync_timestamp(self):
        update_last_sync_timestamp("2026-08-27T10:00:00Z")
        self.assertEqual(get_last_sync_timestamp(), "2026-08-27T10:00:00Z")

    def test_02_collect_telemetry_payload(self):
        payload = self.manager.collect_telemetry_payload()

        self.assertEqual(payload["client_id"], "test-agent-client-001")
        self.assertIn("timestamp", payload)
        self.assertIn(payload["tally_status"], ["ONLINE", "OFFLINE"])
        self.assertGreaterEqual(payload["connector_uptime_seconds"], 0.0)
        self.assertIsNotNone(payload["app_version"])
        self.assertGreaterEqual(payload["cpu_usage_percent"], 0.0)
        self.assertGreaterEqual(payload["memory_usage_mb"], 0.0)
        self.assertIsInstance(payload["pending_queue_count"], int)

    def test_03_send_telemetry_success(self):
        self.mock_cloud_client.send_heartbeat.return_value = {"acknowledged": True}

        result = self.manager.send_telemetry()

        self.assertTrue(result["sent"])
        self.assertIsNone(result["error"])
        self.mock_cloud_client.send_heartbeat.assert_called_once()

    def test_04_non_fatal_error_handling(self):
        self.mock_cloud_client.send_heartbeat.side_effect = Exception("Cloud connection refused")

        result = self.manager.send_telemetry()

        self.assertFalse(result["sent"])
        self.assertIn("Cloud connection refused", result["error"])

    def test_05_heartbeat_loop_start_stop(self):
        self.assertFalse(self.manager.is_running)
        self.manager.start_heartbeat_loop()

        self.assertTrue(self.manager.is_running)
        time.sleep(0.2)

        self.manager.stop_heartbeat_loop()
        self.assertFalse(self.manager.is_running)

if __name__ == "__main__":
    unittest.main()
