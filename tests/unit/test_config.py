"""
Unit tests for Centralized Configuration System (shared/config.py)
"""

import os
import unittest
from pathlib import Path
from shared.config import Settings, Environment, reset_settings, get_settings

class TestConfig(unittest.TestCase):
    def setUp(self):
        reset_settings()
        self.original_env = dict(os.environ)
        for key in ["APP_ENVIRONMENT", "DEBUG", "LOG_LEVEL", "PORT", "CTRLBOOKS_GATEWAY_PORT", "JWT_SECRET", "OTP_PROVIDER_KEY"]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_settings()

    def test_default_configuration(self):
        settings = Settings.load_from_env()
        self.assertEqual(settings.app_name, "CtrlBooks")
        self.assertEqual(settings.app_environment, Environment.DEVELOPMENT)
        self.assertTrue(settings.debug)

    def test_environment_override(self):
        os.environ["APP_ENVIRONMENT"] = "production"
        os.environ["DEBUG"] = "true"
        os.environ["PORT"] = "9090"

        settings = Settings.load_from_env()
        self.assertEqual(settings.app_environment, Environment.PRODUCTION)
        self.assertFalse(settings.debug)
        self.assertEqual(settings.port, 9090)

    def test_secret_masking(self):
        os.environ["JWT_SECRET"] = "super-secret-key-123"
        os.environ["OTP_PROVIDER_KEY"] = "otp-secret-key-456"

        settings = Settings.load_from_env()
        masked = settings.get_masked_dict()

        self.assertEqual(masked["jwt_secret"], "****")
        self.assertEqual(masked["otp_provider_key"], "****")
        self.assertEqual(masked["app_name"], "CtrlBooks")

    def test_required_validation(self):
        settings = Settings(app_name="", db_path="data/test.db")
        with self.assertRaises(ValueError):
            settings.validate_required()

        settings_invalid_port = Settings(app_name="App", port=99999)
        with self.assertRaises(ValueError):
            settings_invalid_port.validate_required()

if __name__ == "__main__":
    unittest.main()
