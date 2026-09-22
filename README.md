# CtrlBooks - Python Modular Microservices Architecture

A local Windows accounting connector inspired by **BizAnalyst** workflows, with clean separation between **Desktop Executable GUI**, **Background Sync Agent**, **Backend Microservices**, and **Shared Core**.

Supports dual accounting software systems:
1. **Tally Prime / Tally ERP 9** (via TDL XML over HTTP)
2. **BUSY Accounting Software** (via isolated provider boundary / Access / SQL / API)

---

## 🏗️ Re-Designed Clean Directory Structure

```text
CtrlBooks/
├── apps/                        # Application Components
│   ├── desktop_app/             # Desktop GUI (ctrlbooks.exe)
│   ├── agent/                   # Background Sync Agent (ctrlbooks_agent.exe)
│   └── backend/                 # Microservices Core (Gateway & Ports 8001–8009)
├── shared/                      # Shared Models, Fingerprint Engine & DB Adapter
├── scripts/                     # Execution, Build & Test Scripts
├── docs/                        # Architecture Documentation
└── data/                        # SQLite Local Database Persistence
```

---

## 🚀 How to Run & Verify

### 1. Install Dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run Automated Verification Suite
```powershell
python scripts/verify_all.py
```

### 3. Run All Backend Microservices
```powershell
python scripts/run_all.py
```

### 4. Launch Desktop GUI Dashboard
```powershell
python apps/desktop_app/main.py
```

### 5. Launch Standalone Local Agent
```powershell
python apps/agent/main.py
```

---

## 📦 Building Standalone Executables (`.exe`)

### Build `ctrlbooks.exe`
```powershell
python scripts/build_desktop.py
```

### Build `ctrlbooks_agent.exe`
```powershell
python scripts/build_agent.py
```

Swagger API Gateway Docs: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**
