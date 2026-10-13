"""
Command handlers for remote cloud commands dispatched by RemoteCommandWorker.
Each handler encapsulates payload normalization and execution for a specific command domain.
"""
from apps.desktop_app.ui.threads.command_handlers.party_command_handler import execute_party_command
from apps.desktop_app.ui.threads.command_handlers.stock_command_handler import (
    execute_create_stock_item_command,
    execute_update_stock_item_command,
)
from apps.desktop_app.ui.threads.command_handlers.voucher_command_handler import execute_voucher_command

__all__ = [
    "execute_party_command",
    "execute_create_stock_item_command",
    "execute_update_stock_item_command",
    "execute_voucher_command",
]

