"""
Unit tests for Structured Logging & Secret Masking (shared/logging_config.py)
"""

import logging
import unittest
from pathlib import Path
from shared.logging_config import setup_logging, SecretMaskingFilter, ContextFormatter

class TestLogging(unittest.TestCase):
    def test_secret_masking_filter(self):
        filter_obj = SecretMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="User login with JWT_SECRET='my-secret-token-123'", args=(), exc_info=None
        )
        filter_obj.filter(record)
        self.assertIn("JWT_SECRET=****", record.msg)
        self.assertNotIn("my-secret-token-123", record.msg)

    def test_context_formatter(self):
        formatter = ContextFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        record = logging.LogRecord(
            name="app.test", level=logging.INFO, pathname="", lineno=0,
            msg="Testing log line", args=(), exc_info=None
        )
        record.request_id = "req-test-999"
        output = formatter.format(record)

        self.assertIn("INFO", output)
        self.assertIn("app.test", output)
        self.assertIn("Testing log line", output)
        self.assertIn("RequestID=req-test-999", output)

if __name__ == "__main__":
    unittest.main()
