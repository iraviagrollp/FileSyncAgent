import json
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError

_IST = ZoneInfo("Asia/Kolkata")


def upload_with_retry(
    s3_client,
    bucket: str,
    local_path: Path,
    s3_key: str,
    max_retries: int,
    backoff_base: int,
    log: logging.Logger,
) -> bool:
    for attempt in range(1, max_retries + 1):
        try:
            s3_client.upload_file(str(local_path), bucket, s3_key)
            s3_client.head_object(Bucket=bucket, Key=s3_key)
            log.info("Uploaded: %s", s3_key)
            return True
        except ClientError as exc:
            log.warning("Upload attempt %d/%d failed — %s: %s", attempt, max_retries, s3_key, exc)
            if attempt < max_retries:
                wait = backoff_base ** attempt
                log.info("Retrying in %ds", wait)
                time.sleep(wait)
    return False


def write_manifest(s3_client, bucket: str, date_iso: str, files: list[dict], log: logging.Logger):
    manifest = {
        "date": date_iso,
        "uploaded_at": datetime.now(_IST).isoformat(),
        "files": [{"type": f["type"], "s3_key": f["s3_key"]} for f in files],
    }
    key = f"raw/{date_iso}/manifest.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )
    log.info("manifest.json → s3://%s/%s", bucket, key)


def send_sns_alert(sns_client, topic_arn: str, message: str, log: logging.Logger):
    try:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject="[FileSyncAgent] Export failed",
            Message=message,
        )
        log.info("SNS alert sent")
    except Exception as exc:
        log.error("Failed to send SNS alert: %s", exc)
