"""
Iravi Agro Life LLP — File Sync Agent

Entry point. Orchestrates:
  1. FUSIL UI automation  → exports Excel files to local folder
  2. S3 upload            → uploads files and writes manifest.json
"""

import argparse
from datetime import date, timedelta
from pathlib import Path

import boto3

from config import Config
from fusil.exporter import FusilExporter, LoginError
from fusil.reports import REPORTS
from upload.s3 import send_sns_alert, upload_with_retry, write_manifest
from utils import setup_logging, within_schedule_window

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"


def main():
    parser = argparse.ArgumentParser(description="Iravi File Sync Agent")
    parser.add_argument("--force", action="store_true", help="Run outside the scheduled window")
    parser.add_argument("--date", help="Export date as YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    config = Config.load(_CONFIG_PATH)
    log = setup_logging(config.log_file)

    log.info("File Sync Agent starting")

    if not args.force and not within_schedule_window(config):
        log.info("Outside schedule window — exiting")
        return

    export_date = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    log.info("Export date: %s", export_date)

    # ---- Step 1: Export from FUSIL ----
    exporter = FusilExporter(config, log, export_date)
    try:
        exporter.launch()
        exporter.connect()
        for report in REPORTS:
            exporter.export_report(report)
    except LoginError as exc:
        log.error("Aborting: %s", exc)
        return  # finally block handles close(); wrong credentials are not an alertable infra failure
    except Exception as exc:
        log.error("Unhandled error during FUSIL automation: %s", exc, exc_info=True)
        exporter.failed_reports.append("__automation__")
    finally:
        exporter.close()

    if exporter.no_data_reports:
        log.info("No data on %s for: %s (skipped — not a failure)", export_date, exporter.no_data_reports)

    if exporter.failed_reports:
        msg = f"Export errors on {export_date} for: {exporter.failed_reports}"
        log.error(msg)
        sns = boto3.client("sns", region_name=config.aws_region)
        send_sns_alert(sns, config.sns_alert_arn, msg, log)
        return

    if not exporter.exported_files:
        log.info("No files exported for %s (all reports had no data) — nothing to upload", export_date)
        return

    # ---- Step 2: Upload to S3 (disabled until AWS account is provisioned) ----
    if not config.s3_upload_enabled:
        log.info("S3 upload disabled — export-only run complete")
        for f in exporter.exported_files:
            log.info("  [%s] %s", f["type"], f["local_path"])
        return

    s3 = boto3.client("s3", region_name=config.aws_region)
    sns = boto3.client("sns", region_name=config.aws_region)
    date_iso = export_date.isoformat()
    uploaded: list[dict] = []

    for file_info in exporter.exported_files:
        local_path: Path = file_info["local_path"]
        s3_key = f"raw/{date_iso}/{local_path.name}"
        success = upload_with_retry(
            s3, config.s3_bucket, local_path, s3_key,
            config.max_retries, config.retry_backoff_seconds, log,
        )
        if not success:
            msg = f"S3 upload failed for {local_path.name} on {date_iso}"
            log.error(msg)
            send_sns_alert(sns, config.sns_alert_arn, msg, log)
            return
        uploaded.append({"type": file_info["type"], "s3_key": s3_key})

    # ---- Step 3: Write manifest (triggers ETL Lambda) ----
    write_manifest(s3, config.s3_bucket, date_iso, uploaded, log)
    log.info("Done — %d file(s) uploaded for %s", len(uploaded), date_iso)


if __name__ == "__main__":
    main()
