

import os
import time
import threading
import psutil
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from sqlalchemy import select, func
from shared.config import get_settings
from shared.logging_config import get_logger
from shared.cloud_client import CloudClient
from shared.db.models.sync import SyncQueue
from shared.db.session import get_db_session

logger = get_logger("app.agent.telemetry")

_GLOBAL_LAST_SYNC_TIMESTAMP: Optional[str] = None

def update_last_sync_timestamp(timestamp_iso: Optional[str] = None) -> None:
    """Updates the globally recorded last sync timestamp."""
    global _GLOBAL_LAST_SYNC_TIMESTAMP
    _GLOBAL_LAST_SYNC_TIMESTAMP = timestamp_iso or datetime.now(timezone.utc).isoformat()

def get_last_sync_timestamp() -> Optional[str]:
    """Returns the globally recorded last sync timestamp."""
    return _GLOBAL_LAST_SYNC_TIMESTAMP

class TelemetryManager:
    def __init__(
        self,
        cloud_client: Optional[CloudClient] = None,
        interval_seconds: int = 60,
    ):
        self.settings = get_settings()
        self.cloud_client = cloud_client or CloudClient()
        self.interval_seconds = interval_seconds
        self.start_time = time.time()
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def probe_software_status(self) -> str:
        """
        Probes active status of Tally Prime.
        Returns 'ONLINE' or 'OFFLINE'.
        """
        tally_status = "OFFLINE"

        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            res = sock.connect_ex((self.settings.tally_host, self.settings.tally_port))
            sock.close()
            if res == 0:
                tally_status = "ONLINE"
        except Exception:
            tally_status = "OFFLINE"

        return tally_status

    def get_system_metrics(self) -> Tuple[float, float]:
        """
        Retrieves CPU usage percentage and RSS Memory usage in Megabytes (MB).
        """
        try:
            proc = psutil.Process(os.getpid())
            cpu = round(psutil.cpu_percent(interval=0.05), 2)
            mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
            return cpu, mem_mb
        except Exception:
            return 0.0, 0.0

    def get_pending_queue_count(self, db_session=None) -> int:
        """
        Queries count of pending or failed queue items in 'sync_queue' table.
        """
        try:
            if db_session is not None:
                stmt = select(func.count(SyncQueue.id)).where(
                    SyncQueue.status.in_(["PENDING", "FAILED"])
                )
                return int(db_session.scalar(stmt) or 0)

            with get_db_session() as session:
                stmt = select(func.count(SyncQueue.id)).where(
                    SyncQueue.status.in_(["PENDING", "FAILED"])
                )
                return int(session.scalar(stmt) or 0)
        except Exception as exc:
            logger.debug(f"Unable to query pending queue count: {exc}")
            return 0

    def collect_telemetry_payload(self, db_session=None) -> Dict[str, Any]:
        """
        Collects comprehensive telemetry dataset for POST /api/v1/connector/heartbeat.
        """
        tally_st = self.probe_software_status()
        cpu_usage, memory_mb = self.get_system_metrics()
        uptime = round(time.time() - self.start_time, 2)
        queue_count = self.get_pending_queue_count(db_session=db_session)
        last_sync = get_last_sync_timestamp()

        return {
            "client_id": self.cloud_client.client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tally_status": tally_st,
            "tallyConnected": (tally_st == "ONLINE"),
            "status": "ONLINE",
            "connector_uptime_seconds": uptime,
            "app_version": self.settings.app_version,
            "last_sync_timestamp": last_sync,
            "cpu_usage_percent": cpu_usage,
            "memory_usage_mb": memory_mb,
            "pending_queue_count": queue_count,
        }

    def send_telemetry(self, db_session=None) -> Dict[str, Any]:
        """
        Transmits telemetry payload to Cloud Server endpoint.
        Guarantees non-fatal background error handling so telemetry failures
        never interrupt main application sync logic.
        """
        try:
            payload = self.collect_telemetry_payload(db_session=db_session)
            res = self.cloud_client.send_heartbeat(payload)
            logger.info(
                f"Heartbeat telemetry sent successfully. (Uptime: {payload['connector_uptime_seconds']}s, "
                f"Tally: {payload['tally_status']}, Queue: {payload['pending_queue_count']})"
            )
            return {"sent": True, "payload": payload, "response": res, "error": None}

        except Exception as exc:
            logger.warning(f"Background heartbeat telemetry failed (non-fatal): {exc}")
            return {"sent": False, "payload": None, "error": str(exc)}

    def start_heartbeat_loop(self) -> None:
        """Starts background daemon thread for sending heartbeat telemetry every 60s."""
        if self.is_running:
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._loop_worker, daemon=True, name="TelemetryHeartbeatThread")
        self._thread.start()
        logger.info(f"Telemetry heartbeat loop started (Interval: {self.interval_seconds}s).")

    def stop_heartbeat_loop(self) -> None:
        """Stops the background telemetry heartbeat thread."""
        logger.info("Stopping telemetry heartbeat loop...")
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _loop_worker(self) -> None:
        """Internal thread target loop."""
        while self.is_running:
            self.send_telemetry()
            sleep_step = 1.0
            slept = 0.0
            while self.is_running and slept < self.interval_seconds:
                time.sleep(sleep_step)
                slept += sleep_step

telemetry_manager = TelemetryManager()
