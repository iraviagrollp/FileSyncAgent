# IRAVI AGRO LIFE LLP — File Sync Agent

## Instructions for Claude

- After every conversation where decisions are made, code is written, or plans change — update this file to reflect the current state.
- Keep the **What Is Built** checklist accurate: tick items as they are completed.
- Keep the **What Is Next** section current: remove completed items, add newly discovered tasks.
- If a technical decision changes, update the relevant section here immediately.
- This file is the single source of truth for project state across sessions — treat it as such.
- **After every code change** — no matter how small — update both this file and `README.md` before closing the task.
- **Proactive doc updates:** Review CLAUDE.md and README.md at the end of every session. If anything is stale, wrong, or newly clarified — update it without being asked. Don't wait for an explicit instruction.
- **Cross-project sync rule:** This project is a component of the master project tracked in `D:\Projects\Iravi\IaC\CLAUDE.md`. When a milestone is reached (agent working end-to-end, deployed to server, etc.), also update the corresponding checklist item in the IaC CLAUDE.md. The IaC file tracks high-level completion only — this file tracks the detail.

---

## Project Overview

The **File Sync Agent** is a Python script that runs on the **FUSIL PRO server** (Windows machine).

FUSIL PRO **cannot do automatic exports** — it is a custom .NET desktop application.
The agent drives the FUSIL UI directly using **pywinauto**, navigates to each report screen,
triggers the Excel export, then uploads all files to AWS S3 and writes a `manifest.json`
that triggers the ETL Lambda.

The agent runs every 15 minutes from 7PM IST via Windows Task Scheduler.

---

## Repository Layout

```
FileSyncAgent/
├── CLAUDE.md                   ← this file
├── README.md                   ← deployment + operations runbook
├── requirements.txt            ← Python dependencies
├── .gitignore
├── flows/                      ← UI screenshots for reference (git-ignored)
├── src/
│   ├── main.py                 ← entry point + orchestration
│   ├── config.py               ← Config dataclass — single source of all configurable properties
│   ├── utils.py                ← logging setup, schedule window check
│   ├── fusil/
│   │   ├── __init__.py
│   │   ├── exporter.py         ← FusilExporter class (launch, login, navigate, export)
│   │   └── reports.py          ← REPORTS list + FILENAME_PREFIX (per-report config)
│   └── upload/
│       ├── __init__.py
│       └── s3.py               ← upload_with_retry, write_manifest, send_sns_alert
├── config/
│   ├── config.example.json     ← template — copy to config.json and fill in
│   └── config.json             ← real config (git-ignored)
├── scripts/
│   └── install.ps1             ← sets up Windows Task Scheduler automatically
├── tests/
│   └── test_file_sync_agent.py ← unit tests
└── logs/                       ← agent writes logs here (git-ignored)
```

---

## Source Files (exported by agent from FUSIL PRO)

The agent drives FUSIL to export **7 Excel files** each evening.
Note: there is no Expenses report — original spec was incorrect.
Date format in filenames: `DD-M-YYYY` (no leading zero on month, e.g. `17-5-2026`).

### File naming patterns

| # | Type | Filename pattern |
|---|---|---|
| 1 | sale | `RGF Sales Book{DD-M-YYYY}({H.MM.SS}).xlsx` |
| 2 | sale_returns | `RGF Sales Return Book{DD-M-YYYY}({H.MM.SS}).xlsx` |
| 3 | purchase | `RGF Purchase Book{DD-M-YYYY}({H.MM.SS}).xlsx` |
| 4 | purchase_returns | `RGF Purchase Return Book{DD-M-YYYY}({H.MM.SS}).xlsx` |
| 5 | stocks | `RGF Current Stock Balances{DD-M-YYYY}({H.MM.SS}).xlsx` |
| 6 | customer_accounts | `Customer Accounts Export File{DD-M-YYYY}({H.MM.SS}).xlsx` |
| 7 | customer_balances | `Customer Balances{DD-M-YYYY}({H.MM.SS}).xlsx` |

---

## FUSIL Menu Paths (per report)

All 7 paths confirmed from `flows/Navigations/Fusil navigations.xlsx`.
Note: there is no Expenses report — original spec was incorrect.
Note: Customer Accounts navigates via the Masters top-level menu, not Reports.

| Type | Menu path | Exported filename prefix |
|---|---|---|
| sale | Reports → RGF → Sales → RGF Sales Book | `RGF Sales Book` |
| sale_returns | Reports → RGF → Sales → RGF Sales Return Book | `RGF Sales Return Book` |
| purchase | Reports → RGF → Purchase → RGF Purchase Book | `RGF Purchase Book` |
| purchase_returns | Reports → RGF → Purchase → RGF Purchase Return Book | `RGF Purchase Return Book` |
| stocks | Reports → RGF → Stock Reports → RGF Current Stock Balances | `RGF Current Stock Balances` |
| customer_balances | Reports → FI Finance → Balance → Customer Balances | `Customer Balances` |
| customer_accounts | Masters → General → Customer Accounts | `Customer Accounts Export File` |

---

## Agent Behaviour

### Trigger
- Windows Task Scheduler runs the script every 15 minutes
- Active window: 7:00 PM – 9:30 PM IST
- Outside this window the script exits immediately (bypass with `--force`)

### Per-run flow
1. Launch `C:\FUSIL INFINITY\FUSILINFINITY.exe` fresh
2. Detect login screen — enter credentials if present; skip if already past login
3. For each of the 7 reports:
   - Navigate menu tree to the report screen
   - Set From Date = To Date = **yesterday** (DD-MM-YYYY)
   - Click View (F1) to load data
   - **Check `Count=N` in the status bar** — if `Count=0`, FUSIL blocks export; skip this report (not a failure)
   - Press Ctrl+X to export → FUSIL writes `.xlsx` to the export folder
   - Dismiss "Export file generated successfully" dialog (click No)
4. Close FUSIL
5. Upload all exported files to `s3://{bucket}/raw/{YYYY-MM-DD}/`
6. Verify each upload with S3 head-object check
7. Write `manifest.json` (triggers ETL Lambda)
8. On any unexpected error: SNS alert

### No-data handling (key behaviour)
FUSIL disables the export button when no data exists for the selected date range.
The agent reads the `Count=N` indicator after View (F1):
- `Count > 0` → proceed with export
- `Count = 0` → log the skip; continue to next report; **do not alert**
- `Count` unreadable → log a warning and attempt export anyway

No-data skips are expected (e.g. no sales on a Sunday). Only unexpected errors trigger SNS alerts.

### Retry + alerting
- On S3 upload failure: retry up to 3 times with exponential backoff (5s, 25s, 125s)
- After 3 failures: publish to SNS topic → email alert
- Unexpected FUSIL automation errors: SNS alert immediately
- Agent writes structured logs to `logs/file_sync_agent.log`

### manifest.json structure
```json
{
  "date": "2026-05-18",
  "uploaded_at": "2026-05-18T19:45:32+05:30",
  "files": [
    { "type": "sale",              "s3_key": "raw/2026-05-18/RGF Sales Book17-05-2026(19.30.00).xlsx" },
    { "type": "sale_returns",      "s3_key": "raw/2026-05-18/RGF Sales Return Book17-05-2026(19.30.00).xlsx" }
  ]
}
```

---

## Configuration (config/config.json)

```json
{
  "fusil_exe_path": "C:\\FUSIL INFINITY\\FUSILINFINITY.exe",
  "fusil_username": "Administrator",
  "fusil_password": "<secret>",
  "export_folder": "C:\\FUSIL INFINITY\\ExportFiles",
  "s3_upload_enabled": false,
  "s3_bucket": "iravi-dashboard-<account-id>",
  "aws_region": "ap-south-1",
  "sns_alert_arn": "arn:aws:sns:ap-south-1:<account-id>:iravi-dashboard-alerts",
  "schedule_window_start_ist": "19:00",
  "schedule_window_end_ist":   "21:30",
  "max_retries": 3,
  "retry_backoff_seconds": 5,
  "log_file": "D:\\Projects\\Iravi\\FileSyncAgent\\logs\\file_sync_agent.log"
}
```

---

## Open Questions

- [ ] Should the agent **delete/archive** local files after successful S3 upload?

---

## AWS Dependencies (provided by IaC repo after terraform apply)

| Resource | Value |
|---|---|
| S3 bucket | `terraform output` from IaC repo |
| SNS ARN | `terraform output sns_alerts_arn` from IaC repo |
| AWS credentials | IAM user `iravi-admin` access keys (configured via `aws configure`) |

---

## What Is Built

- [x] Project structure created
- [x] CLAUDE.md with full spec
- [x] README.md with deployment runbook
- [x] `config/config.example.json`
- [x] `requirements.txt` (boto3, pywinauto, comtypes, tzdata)
- [x] `src/` — modular structure (main.py, config.py, utils.py, fusil/, upload/)
  - [x] All 7 report menu paths wired up in `fusil/reports.py`
  - [x] No-data detection via `Count=N` status bar (skip without alert)
  - [x] S3 upload disabled via `s3_upload_enabled: false` flag
  - [x] Stale file prevention — `_find_exported_file` filters by `st_mtime >= export_started`
  - [x] Login detection fixed — checks for main window absence; uses `descendants()` for nested form fields
  - [x] S3 upload catches `BotoCoreError` and `OSError` in addition to `ClientError`
- [x] Deployed to FUSIL PRO server (`D:\Iravi InHouse\Software\FileSyncAgent`) — first test run attempted
- [x] `flows/setup-and-run.html` — setup and run guide
- [x] `flows/architecture.html` — system architecture diagram
- [ ] `scripts/install.ps1` — Task Scheduler setup
- [ ] `tests/test_file_sync_agent.py`

## What Is Next

- [ ] Fix menu navigation — control type for FUSIL menu items unknown (running diagnostic)
- [ ] Complete first successful end-to-end export run on FUSIL PRO server
- [ ] Verify Purchase Return Book menu path against live FUSIL app
- [ ] Enable S3 upload once AWS account is provisioned (`s3_upload_enabled: true`)
- [ ] Write `scripts/install.ps1`
- [ ] Write unit tests

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Language | Python 3.9+ | boto3 for S3/SNS, pywinauto for UI automation |
| UI automation | pywinauto UIA backend | .NET desktop app; UIA is the most stable approach for WinForms/WPF |
| FUSIL launch | Fresh launch each run | Avoids stale state from previous sessions |
| Login handling | Detect dynamically | Login screen does not always appear (session persists) |
| AWS SDK | boto3 | Standard Python AWS SDK |
| Scheduling | Windows Task Scheduler | Already available on server, no extra install |
| Logging | Python logging → rotating file | Simple, readable, no external dependency |
| Retry strategy | Exponential backoff | Handles transient S3/network errors |
| No-data handling | Read `Count=N` status bar after View | FUSIL blocks export on empty results; skip gracefully without alerting |
| Error vs no-data | Separate `failed_reports` / `no_data_reports` lists | Only real errors trigger SNS; no-data is an expected business scenario |
| Config loading | Typed `Config` dataclass + `Config.load()` | Single place to see all settings; IDE autocomplete; no stringly-typed key access |
| Modular structure | `fusil/`, `upload/`, `config.py`, `utils.py` | Separates UI automation from S3 logic; per-report config data in `reports.py` |
| Window detection | `Desktop(backend="uia")` matching title `"Fusil"` | Actual OS window title is `"Fusil"` — `"IRAVIAGROLIFELLP"` is a label inside the window, not the OS title. Confirmed via diagnostic script. |
| Menu navigation | Hamburger via `MainMenu1`→`MainMenu` (two-step), top-level items by `auto_id`, sub-items by title in popup | Hamburger is `MenuItem auto_id='MainMenu'` inside `Menu auto_id='MainMenu1'`. Top-level items have `auto_id == title`. Confirmed via diagnostic. |
| Login detection | Count Edit fields: >1 = login screen | Login screen has 4 Edit fields; main screen also has 4+. No post-login verification — count-based check caused false LoginErrors. Wrong credentials surface as menu navigation failures. |
| Login field detection | Find username/password by current value (non-empty vs empty) | 4 edit fields exist — positional indexing unreliable; value-based detection identifies correct fields. `triple_click_input` not available on UIA EditWrapper — use `type_keys("^a") + type_keys(value)`. |
| Login security | Exception logged at DEBUG only (not WARNING) | pywinauto exceptions can echo typed keys — password must not appear in log files |
| Stale file prevention | Filter exported files by `st_mtime >= export_started` | Prevents returning a file from a prior run if the current export silently fails |
