

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.connector import Connector, DataSource, Destination, FieldMapping
from shared.db.models.metadata import UnifiedSourceMetadata, MetadataDiscoveryRun
from shared.db.models.extraction import DataExtractionRun
from shared.db.models.mapping import MappingDefinition, MappingVersion, MappingFieldRule, MappingValidationLog
from shared.db.models.sync import SyncJobV2, SyncError, SyncCheckpoint
from shared.db.models.system import ActivityLog, Notification, HealthHistory
from shared.db.models.storage import ExtractedRecord
from shared.db.models.company import CompanySyncConfig

def main():
    print("=========================================================")
    print(" CtrlBooks - Complete Demo & Test Data Cleanup")
    print("=========================================================")
    
    initialize_database()

    with get_db_session() as db:
        cnt_ext_rec = db.query(ExtractedRecord).delete(synchronize_session=False)
        db.query(CompanySyncConfig).delete(synchronize_session=False)
        cnt_conn = db.query(Connector).delete(synchronize_session=False)
        cnt_ds = db.query(DataSource).delete(synchronize_session=False)
        cnt_dest = db.query(Destination).delete(synchronize_session=False)
        db.query(FieldMapping).delete(synchronize_session=False)

        cnt_meta = db.query(UnifiedSourceMetadata).delete(synchronize_session=False)
        cnt_metarun = db.query(MetadataDiscoveryRun).delete(synchronize_session=False)

        cnt_ext = db.query(DataExtractionRun).delete(synchronize_session=False)

        cnt_map = db.query(MappingDefinition).delete(synchronize_session=False)
        db.query(MappingVersion).delete(synchronize_session=False)
        cnt_mfr = db.query(MappingFieldRule).delete(synchronize_session=False)
        db.query(MappingValidationLog).delete(synchronize_session=False)

        cnt_sync = db.query(SyncJobV2).delete(synchronize_session=False)
        db.query(SyncError).delete(synchronize_session=False)
        db.query(SyncCheckpoint).delete(synchronize_session=False)

        cnt_logs = db.query(ActivityLog).delete(synchronize_session=False)
        db.query(Notification).delete(synchronize_session=False)
        db.query(HealthHistory).delete(synchronize_session=False)

        db.commit()

    from shared.db.mongo_client import get_collection
    raw_collections = [
        "normalized_records",
        "companies",
        "change_events",
        "audit_events",
        "sync_jobs",
        "event_queue",
        "sync_queue"
    ]
    for c_name in raw_collections:
        try:
            get_collection(c_name).delete_many({})
        except Exception:
            pass

    print(f"[+] Deleted {cnt_ext_rec} extracted records.")
    print(f"[+] Deleted {cnt_conn} connectors, {cnt_ds} sources, {cnt_dest} destinations.")
    print(f"[+] Deleted {cnt_meta} metadata entries, {cnt_metarun} discovery runs.")
    print(f"[+] Deleted {cnt_ext} extraction runs.")
    print(f"[+] Deleted {cnt_map} mapping definitions, {cnt_mfr} field rules.")
    print(f"[+] Deleted {cnt_sync} sync jobs, {cnt_logs} activity logs.")
    print("\n[+] All demo and test data successfully cleaned! Database is fresh and ready.\n")

if __name__ == "__main__":
    main()
