"""
Unit tests for Windows Startup & Registry Integration (shared/system_startup.py).
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from shared.system_startup import (
    enable_run_on_startup,
    disable_run_on_startup,
    is_startup_enabled,
    DEFAULT_APP_NAME,
)


class TestSystemStartupUnit(unittest.TestCase):

    @patch("os.name", "nt")
    @patch("winreg.OpenKey")
    @patch("winreg.SetValueEx")
    @patch("winreg.CloseKey")
    def test_01_enable_run_on_startup(self, mock_close, mock_set_val, mock_open_key):
        mock_key = MagicMock()
        mock_open_key.return_value = mock_key

        res = enable_run_on_startup("TestApp", r"C:\App\test.exe")

        self.assertTrue(res)
        mock_open_key.assert_called_once()
        mock_set_val.assert_called_once()

    @patch("os.name", "nt")
    @patch("winreg.OpenKey")
    @patch("winreg.DeleteValue")
    @patch("winreg.CloseKey")
    def test_02_disable_run_on_startup(self, mock_close, mock_del_val, mock_open_key):
        mock_key = MagicMock()
        mock_open_key.return_value = mock_key

        res = disable_run_on_startup("TestApp")

        self.assertTrue(res)
        mock_del_val.assert_called_once()

    @patch("os.name", "nt")
    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    @patch("winreg.CloseKey")
    def test_03_is_startup_enabled_true(self, mock_close, mock_query, mock_open_key):
        mock_key = MagicMock()
        mock_open_key.return_value = mock_key
        mock_query.return_value = (r'"C:\App\test.exe"', 1)

        res = is_startup_enabled("TestApp")

        self.assertTrue(res)
        mock_query.assert_called_once()

    @patch("os.name", "nt")
    @patch("winreg.OpenKey", side_effect=FileNotFoundError)
    def test_04_is_startup_enabled_false(self, mock_open_key):
        res = is_startup_enabled("NonExistentApp")
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
