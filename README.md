# ToolHub

Infosec uploads a verified tool inventory (Excel). Users look up tools by name and get Yes/No + status.

## Run locally

```bash
cd tool-availability-lookup
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**

## Logins

| User    | Password | Role    |
|---------|----------|---------|
| infosec | infosec  | Upload verified inventory |
| user    | user     | Lookup tools |
| admin   | admin    | Admin |
| auditor | auditor  | View audit log |

## Usage

1. **Infosec:** Upload Excel (.xlsx) with columns **Tool Name**, **Vendor** (optional: Version, Notes, Status).
2. **User:** **Lookup tool** → type tool name → see Yes/No and status.
