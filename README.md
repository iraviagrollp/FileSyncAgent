# IRAVI File Sync Agent

Drives the FUSIL PRO desktop application via UI automation, exports 7 nightly Excel reports,
and uploads them to AWS S3 — triggering the ETL pipeline.

---

## What It Does

```
Windows Task Scheduler (every 15 min, 7–9:30 PM IST)
        ↓
Launch FUSIL PRO (FUSILINFINITY.exe)
        ↓
Login if needed (detects login screen dynamically)
        ↓
For each of 7 reports:
  Navigate menu → set yesterday's date → View (F1)
  Count=0? → skip (no data, not a failure)
  Count>0? → Ctrl+X export → dismiss dialog
        ↓
Close FUSIL
        ↓  s3_upload_enabled=true
Upload 7 × .xlsx  →  S3: raw/{date}/
        ↓
Write manifest.json  ←  triggers ETL Lambda
        ↓
On any failure: retry 3× → SNS email alert
```

---

## Project Structure

```
FileSyncAgent/
├── src/
│   ├── main.py                 ← entry point + orchestration
│   ├── config.py               ← Config dataclass (all settings in one place)
│   ├── utils.py                ← logging setup, schedule window check
│   ├── fusil/
│   │   ├── exporter.py         ← FusilExporter: launch, login, navigate, export
│   │   └── reports.py          ← menu paths + filename prefixes for all 7 reports
│   └── upload/
│       └── s3.py               ← upload_with_retry, write_manifest, send_sns_alert
├── config/
│   ├── config.example.json     ← copy this to config.json and fill in
│   └── config.json             ← real values (never commit — git-ignored)
├── scripts/
│   └── install.ps1             ← Task Scheduler setup (pending)
├── tests/
│   └── test_file_sync_agent.py ← unit tests (pending)
└── logs/                       ← runtime logs (auto-created)
```

---

## Prerequisites

- Python 3.9+ on the FUSIL PRO server (confirmed: `D:\Runtimes\Python313`)
- FUSIL PRO installed at `C:\FUSIL INFINITY\FUSILINFINITY.exe`
- AWS CLI configured: `aws configure` (use `iravi-admin` access keys)
- Network access from the server to AWS S3 / SNS (ap-south-1)

---

## Setup

**1. Clone the repo**
```powershell
git clone https://github.com/your-org/FileSyncAgent.git
cd FileSyncAgent
```

**2. Install dependencies**
```powershell
pip install -r requirements.txt
```

**3. Create config**
```powershell
copy config\config.example.json config\config.json
# Edit config.json — fill in fusil_password, and S3/SNS values once AWS is provisioned
```

**4. Install Task Scheduler job** *(once install.ps1 is written)*
```powershell
# Run as Administrator
.\scripts\install.ps1
```

---

## Running Manually

```powershell
python src\main.py
```

Pass `--force` to run outside the 7 PM – 9:30 PM IST window:

```powershell
python src\main.py --force
```

Export a specific date instead of yesterday:

```powershell
python src\main.py --force --date 2026-05-17
```

---

## Reports Exported

| Report | Menu Path |
|---|---|
| Sale | Reports → RGF → Sales → RGF Sales Book |
| Sale Returns | Reports → RGF → Sales → RGF Sales Return Book |
| Purchase | Reports → RGF → Purchase → RGF Purchase Book |
| Purchase Returns | Reports → RGF → Purchase → RGF Purchase Return Book |
| Stocks | Reports → RGF → Stock Reports → RGF Current Stock Balances |
| Customer Balances | Reports → FI Finance → Balance → Customer Balances |
| Customer Accounts | Masters → General → Customer Accounts |

---

## Logs

Logs are written to the path set in `config.json → log_file`. Example output:

```
2026-05-18 19:30:01 INFO     File Sync Agent starting
2026-05-18 19:30:01 INFO     Export date: 2026-05-17
2026-05-18 19:30:01 INFO     Launching FUSIL: C:\FUSIL INFINITY\FUSILINFINITY.exe
2026-05-18 19:30:07 INFO     Login screen detected — entering credentials
2026-05-18 19:30:12 INFO     Main window ready
2026-05-18 19:30:13 INFO     === SALE ===
2026-05-18 19:30:13 INFO     Menu: Reports → RGF → Sales → RGF Sales Book
2026-05-18 19:30:30 INFO     File found: RGF Sales Book17-05-2026(19.30.30).xlsx
...
2026-05-18 19:35:42 INFO     S3 upload disabled — export-only run complete
```

---

## S3 Layout *(when s3_upload_enabled = true)*

```
s3://{bucket}/
└── raw/
    └── 2026-05-17/
        ├── RGF Sales Book17-5-2026(19.30.00).xlsx
        ├── RGF Sales Return Book17-5-2026(19.30.00).xlsx
        ├── RGF Purchase Book17-5-2026(19.30.00).xlsx
        ├── RGF Purchase Return Book17-5-2026(19.30.00).xlsx
        ├── RGF Current Stock Balances17-5-2026(19.30.00).xlsx
        ├── Customer Balances17-5-2026(19.30.00).xlsx
        ├── Customer Accounts Export File17-5-2026(19.30.00).xlsx
        └── manifest.json   ← written last, triggers ETL Lambda
```

---

## Troubleshooting

**Login screen not detected / agent skips login**
→ Fixed in latest version (uses `descendants()` to find nested form fields). Pull latest and retry.

**Menu navigation fails**
→ Check logs for `menu_select failed` — the agent falls back to manual clicks automatically. If both fail, the report is logged as failed and an SNS alert is sent.

**No exported file found after export step**
→ Confirm `export_folder` in `config.json` matches the folder FUSIL actually writes to. Export manually in FUSIL and check where the file appears.

**S3 upload fails with credentials error**
→ Run `aws sts get-caller-identity`. If it fails, re-run `aws configure` with `iravi-admin` keys.

**SNS alert not arriving**
→ Confirm the SNS subscription — click the confirmation link in the AWS email sent to iraviagrollp@gmail.com.

**Agent exits immediately without running**
→ Outside the 7:00 PM – 9:30 PM IST window. Use `--force` flag to bypass.
