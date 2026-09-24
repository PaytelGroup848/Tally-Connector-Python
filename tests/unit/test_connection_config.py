import unittest
from unittest.mock import patch, MagicMock
from shared.connection_config import (
    load_connection_config,
    save_connection_config,
    get_configured_port,
    get_configured_host,
    test_tally_port,
)


class TestConnectionConfig(unittest.TestCase):
    def test_save_and_load_config(self):
        # Save a custom port (e.g. 9025 for shared cloud server)
        ok = save_connection_config(host="127.0.0.1", port=9025, sync_interval_minutes="15 mins", auto_connect=False)
        self.assertTrue(ok)

        self.assertEqual(get_configured_port(), 9025)
        self.assertEqual(get_configured_host(), "127.0.0.1")

        cfg = load_connection_config()
        self.assertEqual(cfg.get("tally_port"), 9025)
        self.assertEqual(cfg.get("sync_interval_minutes"), "15 mins")
        self.assertFalse(cfg.get("auto_connect"))

    def test_reset_to_default(self):
        # Reset back to standard 9000
        ok = save_connection_config(host="127.0.0.1", port=9000, auto_connect=True)
        self.assertTrue(ok)
        self.assertEqual(get_configured_port(), 9000)

    @patch("socket.socket")
    def test_tally_port_socket_refused(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # Connection refused
        mock_socket_cls.return_value = mock_sock

        is_online, comps, msg = test_tally_port(port=9099)
        self.assertFalse(is_online)
        self.assertEqual(comps, [])
        self.assertIn("not responding", msg)


if __name__ == "__main__":
    unittest.main()

