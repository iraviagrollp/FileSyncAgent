# IRAVI File Sync Agent

Watches the FUSIL PRO export folder for 8 nightly Excel files and uploads them to AWS S3, triggering the ETL pipeline.

---

## What It Does

```
FUSIL PRO export folder  (local, Windows)
        ↓  detected by agent (runs every 15 min, 7–9:30 PM IST)
All 8 files present?
        ↓  yes
Upload to S3: raw/{date}/*.xlsx
        ↓
Write manifest.json  ← triggers ETL Lambda
        ↓
On failure: retry 3× → SNS email alert
```

---

## Project Structure

```
FileSyncAgent/
├── src/
│   └── file_sync_agent.py      ← main script
├── config/
│   ├── config.example.json     ← copy this to config.json and fill in
│   └── config.json             ← real values (never commit this)
├── scripts/
│   └── install.ps1             ← Task Scheduler setup
├── tests/
│   └── test_file_sync_agent.py
└── logs/                       ← runtime logs (auto-created)
```

---

## Prerequisites

- Python 3.9+ installed on the FUSIL PRO server
- AWS CLI configured: `aws configure` (use `iravi-admin` access keys)
- Network access from the server to AWS S3 / SNS

---

## Setup

**1. Install dependencies**
```powershell
pip install -r requirements.txt
```

**2. Create config**
```powershell
Copy-Item config\config.example.json config\config.json
# Edit config.json with the real folder path, S3 bucket, SNS ARN
```

**3. Install Task Scheduler job**
```powershell
# Run as Administrator
.\scripts\install.ps1
```

This creates a Windows Task Scheduler job that runs the agent every 15 minutes between 7:00 PM and 9:30 PM IST.

---

## Running Manually

```powershell
python src\main.py
```

Useful for testing outside the scheduled window. Pass `--force` to skip the time-window check:

```powershell
python src\main.py --force
```

---

## Logs

Logs are written to `logs\file_sync_agent.log`. Each run appends a structured entry:

```
2026-05-18 19:30:01 INFO  Starting File Sync Agent for date 2026-05-18
2026-05-18 19:30:01 INFO  Found 8/8 files in export folder
2026-05-18 19:30:04 INFO  Uploaded: RGF Sales Book18-5-2026(19.30.00).xlsx
...
2026-05-18 19:30:09 INFO  manifest.json written — pipeline triggered
```

---

## Troubleshooting

**Agent runs but finds 0 files**
→ Check `export_folder` in `config.json` matches the actual FUSIL PRO export path.

**Upload fails with credentials error**
→ Run `aws sts get-caller-identity` — if it fails, re-run `aws configure`.

**Only N of 8 files found**
→ FUSIL PRO hasn't finished exporting yet. Agent will retry on the next 15-min trigger.

**SNS alert not arriving**
→ Check the SNS subscription is confirmed (click the link in the AWS confirmation email).

---

## S3 Layout

```
s3://{bucket}/
└── raw/
    └── 2026-05-18/
        ├── RGF Sales Book18-5-2026(19.30.00).xlsx
        ├── RGF Sales Return Book18-5-2026(19.30.00).xlsx
        ├── RGF Purchase Book18-5-2026(19.30.00).xlsx
        ├── RGF Purchase Return Report18-5-2026(19.30.00).xlsx
        ├── RGF Expenses18-5-2026(19.30.00).xlsx
        ├── Stocks.xlsx
        ├── Customer Accounts Export File18-5-2026(19.30.00).xlsx
        ├── Customer Balances18-5-2026(19.30.00).xlsx
        └── manifest.json                ← written last, triggers ETL
```
