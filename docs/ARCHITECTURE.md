# CtrlBooks - Re-Designed Modular Architecture Guide
*(Dual Software Support: Tally Prime & BUSY Accounting)*

Welcome to the updated **CtrlBooks** architecture documentation.
The project is organized into a clean, service-oriented structure isolating the **Desktop Application GUI (`ctrlbooks.exe`)**, the **Local Sync Agent (`ctrlbooks_agent.exe`)**, the **Backend Microservices Core**, and **Shared Libraries**.

---

## 1. System Architecture Overview

```text
+-------------------------------------------------------------------------+
|                    Desktop App (ctrlbooks.exe)              |
|                             (apps/desktop_app)                          |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  Local Sync Agent (ctrlbooks_agent.exe)                        |
|                               (apps/agent)                              |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                        API Gateway (Port 8000)                          |
|                          (apps/backend/gateway)                         |
+-------------------------------------------------------------------------+
                                     |
            +------------------------+------------------------+
            |                                                 |
            v                                                 v
+-----------------------+                         +-----------------------+
|  Tally Adapter (8002) |                         |  BUSY Adapter (8003)  |
|  (apps/backend/...)   |                         |  (apps/backend/...)   |
+-----------+-----------+                         +-----------+-----------+
            \                                                 /
             +-----------------------+-----------------------+
                                     |
                                     v
                     +-------------------------------+
                     | Normalization Service (8004)  |
                     +---------------+---------------+
                                     |
                                     v
                     +-------------------------------+
                     | Change Detection Svc (8006)   |
                     +---------------+---------------+
                                     |
                                     v
                     +-------------------------------+
                     |   Storage Service (8007)      | (SQLite: data/ctrlbooks.db)
                     +-------------------------------+
```

---

## 2. Directory Structure

```text
CtrlBooks/
├── apps/                        # Application Entry Points
│   ├── desktop_app/             # Desktop App GUI (ctrlbooks.exe target)
│   │   ├── main.py              # Tkinter GUI & status dashboard entry point
│   │   ├── ui.py                # Dashboard & Live Activity Log UI component
│   │   └── ctrlbooks.spec # PyInstaller build spec
│   ├── agent/                   # Local Sync Agent (ctrlbooks_agent.exe target)
│   │   ├── main.py              # Standalone background agent entry point
│   │   ├── agent_service.py     # Tally & BUSY background sync watcher
│   │   └── ctrlbooks_agent.spec        # PyInstaller build spec
│   └── backend/                 # Backend Microservices Hub
│       ├── gateway/             # API Gateway (Port 8000)
│       │   └── main.py
│       └── services/            # Isolated Microservices (Ports 8001–8009)
│           ├── connection_service/       # Port 8001: Connectivity status prober
│           ├── tally_adapter/            # Port 8002: TDL XML over HTTP adapter
│           ├── busy_adapter/             # Port 8003: BUSY provider boundary
│           ├── normalization_service/    # Port 8004: Data normalization engine
│           ├── sync_service/             # Port 8005: Sync orchestrator service
│           ├── change_detection_service/ # Port 8006: SHA-256 fingerprint diffing
│           ├── storage_service/          # Port 8007: SQLite persistence layer
│           ├── audit_service/            # Port 8008: Audit trail service
│           └── company_service/          # Port 8009: Company management service
├── shared/                      # Shared Contracts & Core Utilities
│   ├── database.py              # Thread-safe SQLite DB manager
│   ├── fingerprint.py           # SHA-256 data hashing engine
│   └── models.py                # Unified Pydantic data schemas
├── scripts/                     # Execution, Verification & Build Scripts
│   ├── run_all.py               # Launcher for microservices
│   ├── verify_all.py            # Automated health & pipeline test suite
│   ├── build_desktop.py         # PyInstaller builder for ctrlbooks.exe
│   └── build_agent.py           # PyInstaller builder for ctrlbooks_agent.exe
├── docs/                        # Project Documentation
│   └── ARCHITECTURE.md
├── data/                        # Local Storage Directory (ctrlbooks.db)
├── requirements.txt
└── README.md
```

---

## 3. Microservices & Port Reference

| Service Name | Port | Location | Description |
|---|---|---|---|
| **API Gateway** | `8000` | `apps/backend/gateway/main.py` | Central entry point routing external requests |
| **Connection Service** | `8001` | `apps/backend/services/connection_service` | Probes live Tally (HTTP) & BUSY (Process/DB) |
| **Tally Adapter** | `8002` | `apps/backend/services/tally_adapter` | TDL XML request generator & extractor |
| **BUSY Adapter** | `8003` | `apps/backend/services/busy_adapter` | Provider boundary for BUSY MS Access/SQL/API |
| **Normalization Service** | `8004` | `apps/backend/services/normalization_service` | Converts raw records to canonical LR format |
| **Sync Service** | `8005` | `apps/backend/services/sync_service` | Background sync orchestrator |
| **Change Detection** | `8006` | `apps/backend/services/change_detection_service` | SHA-256 fingerprint diff engine |
| **Storage Service** | `8007` | `apps/backend/services/storage_service` | SQLite thread-safe persistence layer |
| **Audit Service** | `8008` | `apps/backend/services/audit_service` | System audit trail and event logger |
| **Company Service** | `8009` | `apps/backend/services/company_service` | Tally & BUSY company registration |

---

## 4. How to Build Executables

### Build Desktop App (`ctrlbooks.exe`)
```powershell
python scripts/build_desktop.py
```
Output: `dist/ctrlbooks/ctrlbooks.exe`

### Build Local Agent (`ctrlbooks_agent.exe`)
```powershell
python scripts/build_agent.py
```
Output: `dist/ctrlbooks_agent/ctrlbooks_agent.exe`
