"""
CtrlBooks - Global Tally Sequential Request Coordinator
-------------------------------------------------------
Tally Prime's embedded HTTP server (Port 9000) is single-threaded and runs on the
same thread as Tally's core accounting engine and UI message loop.
Concurrent HTTP requests to Tally trigger:
- Software Exception c00000fd (Stack overflow crash)
- Software Exception c0000005 (Memory Access Violation crash)
- UI freezing / "Not Responding" hangs

This coordinator guarantees that exactly ONE request is sent to Tally at a time,
queuing all callers safely and providing cooperative breathing delays.
"""

import threading
import time

_TALLY_LOCK = threading.RLock()


def get_tally_lock() -> threading.RLock:
    """Returns the shared re-entrant lock for all Tally Prime communications."""
    return _TALLY_LOCK

