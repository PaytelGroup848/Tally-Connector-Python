

import time
import httpx
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger

from apps.agent.telemetry import TelemetryManager, update_last_sync_timestamp

setup_logging("agent")
logger = get_logger("app.agent")
settings = get_settings()

GATEWAY_URL = f"http://{settings.host}:{settings.port}"

class LRAgentWorker:
    def __init__(self, interval_seconds: int = 30):
        self.interval_seconds = interval_seconds
        self.is_running = False
        self.telemetry = TelemetryManager(interval_seconds=60)

    def start(self):
        """Starts the agent background loop and telemetry heartbeat."""
        self.is_running = True
        logger.info(f"CtrlBooks Agent started. Polling interval: {self.interval_seconds}s")
        self.telemetry.start_heartbeat_loop()
        
        while self.is_running:
            try:
                self.run_sync_cycle()
            except Exception as exc:
                logger.error(f"Error during agent sync cycle: {exc}")
            
            time.sleep(self.interval_seconds)

    def stop(self):
        """Stops the agent background loop and telemetry heartbeat."""
        logger.info("Stopping CtrlBooks Agent worker...")
        self.is_running = False
        self.telemetry.stop_heartbeat_loop()

    def run_sync_cycle(self):
        """Executes a single extraction & sync cycle for Tally."""
        logger.info("--- Starting Local Sync Cycle ---")

        try:
            res_status = httpx.get(f"{GATEWAY_URL}/api/status", timeout=5)
            if res_status.status_code == 200:
                st = res_status.json()
                logger.info(f"Connection Probe: Tally={st.get('tally', {}).get('state')}")
        except Exception as e:
            logger.warning(f"Unable to reach API Gateway status endpoint at {GATEWAY_URL}: {e}")
            return

        active_companies = []
        try:
            res_comp = httpx.get(f"{GATEWAY_URL}/api/companies", timeout=5)
            if res_comp.status_code == 200:
                c_data = res_comp.json()
                if isinstance(c_data, list):
                    for c in c_data:
                        name = c.get("name") or c.get("company_name")
                        if name and name not in active_companies:
                            active_companies.append(name)
        except Exception:
            pass

        if not active_companies:
            try:
                from shared.db.mongo_client import get_collection
                c_docs = list(get_collection("companies").find({}, {"company_name": 1, "name": 1}).limit(10))
                for c in c_docs:
                    name = c.get("company_name") or c.get("name")
                    if name and name not in active_companies:
                        active_companies.append(name)
            except Exception:
                pass

        for comp_name in active_companies:
            try:
                payload = {
                    "source": "tally",
                    "company_name": comp_name,
                    "full_sync": True
                }
                res_sync = httpx.post(f"{GATEWAY_URL}/api/sync/start", json=payload, timeout=10)
                if res_sync.status_code == 200:
                    job_data = res_sync.json()
                    logger.info(f"Sync Job initiated for '{comp_name}': Job ID={job_data.get('job_id')}")
                    update_last_sync_timestamp()
                else:
                    logger.warning(f"Sync trigger for '{comp_name}' responded with status code: {res_sync.status_code}")
            except Exception as e:
                logger.error(f"Sync execution failed for '{comp_name}': {e}")

        try:
            from shared.db.session import get_db_session
            from apps.backend.services.queue_service import queue_service
            with get_db_session() as db_session:
                res_queue = queue_service.process_queue_batch(db_session=db_session)
                if res_queue.get("total", 0) > 0:
                    logger.info(f"Sync Queue Processed: Total={res_queue['total']}, Synced={res_queue['synced']}, Failed={res_queue['failed']}")
        except Exception as e:
            logger.error(f"Failed to process sync queue: {e}")

        try:
            from shared.cloud_client import CloudClient
            cloud_client = CloudClient()
            pending_invoices = cloud_client.get_pending_invoices(limit=10)
            if pending_invoices:
                logger.info(f"Inbound Sync: Found {len(pending_invoices)} pending invoices from cloud.")
                for inv in pending_invoices:
                    inv_id = str(inv.get("invoice_id") or inv.get("id") or "").strip()
                    if not inv_id:
                        continue
                    logger.info(f"Inbound Sync: Processing invoice {inv_id}...")
                    
                    inv_comp = (
                        inv.get("company_name")
                        or inv.get("company")
                        or (active_companies[0] if active_companies else "")
                    )
                    import_payload = {
                        "company_name": inv_comp,
                        "voucher_type": inv.get("voucher_type", "Sales"),
                        "date": inv.get("date"),
                        "voucher_number": inv_id,
                        "party_ledger": inv.get("party_name"),
                        "amount": inv.get("total_amount", 0.0),
                        "items": inv.get("items", [])
                    }
                    
                    try:
                        import_res = httpx.post(f"{GATEWAY_URL}/api/v1/connector/invoices/import", json=import_payload, timeout=20)
                        if import_res.status_code == 200:
                            res_data = import_res.json()
                            if res_data.get("status") == "SUCCESS":
                                v_num = res_data.get("voucher_number") or inv_id
                                cloud_client.acknowledge_invoice(inv_id, "SUCCESS", voucher_number=v_num)
                                logger.info(f"Inbound Sync: Successfully imported and acknowledged invoice {inv_id} (Tally Vch: {v_num}).")
                            else:
                                err_msg = res_data.get("error") or "Unknown import error"
                                cloud_client.acknowledge_invoice(inv_id, "FAILED", error_message=err_msg)
                                logger.error(f"Inbound Sync: Import failed for invoice {inv_id}: {err_msg}")
                        else:
                            cloud_client.acknowledge_invoice(inv_id, "FAILED", error_message=f"HTTP status code {import_res.status_code}")
                            logger.error(f"Inbound Sync: Adapter returned status code {import_res.status_code} for invoice {inv_id}")
                    except Exception as e:
                        logger.error(f"Inbound Sync: Connection error importing invoice {inv_id}: {e}")
                        try:
                            cloud_client.acknowledge_invoice(inv_id, "FAILED", error_message=str(e))
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Failed during inbound sync loop: {e}")

        logger.info("--- Sync Cycle Completed ---")
