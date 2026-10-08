import unittest
from unittest.mock import patch, MagicMock
from shared.connection_config import (
    load_connection_config,
    save_connection_config,
    get_configured_port,
    get_configured_host,
    test_tally_port as check_tally_port,
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

    @patch("shared.connection_config.is_socket_open")
    def test_resolve_active_tally_port_with_open_port(self, mock_socket_open):
        from shared.connection_config import resolve_active_tally_port
        mock_socket_open.return_value = True

        save_connection_config(host="127.0.0.1", port=9047)
        h, p = resolve_active_tally_port()
        self.assertEqual(h, "127.0.0.1")
        self.assertEqual(p, 9047)

    @patch("shared.connection_config.is_socket_open")
    def test_resolve_active_tally_port_with_preferred(self, mock_socket_open):
        from shared.connection_config import resolve_active_tally_port
        mock_socket_open.return_value = True

        h, p = resolve_active_tally_port(preferred_port=9088, preferred_host="127.0.0.1")
        self.assertEqual(h, "127.0.0.1")
        self.assertEqual(p, 9088)


if __name__ == "__main__":
    unittest.main()

