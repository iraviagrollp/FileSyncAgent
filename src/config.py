import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # FUSIL application
    fusil_exe_path: str
    fusil_username: str
    fusil_password: str
    export_folder: str

    # AWS
    s3_bucket: str
    aws_region: str
    sns_alert_arn: str

    # Schedule
    schedule_window_start_ist: str
    schedule_window_end_ist: str

    # Retry
    max_retries: int
    retry_backoff_seconds: int

    # Logging
    log_file: str

    # Feature flags
    s3_upload_enabled: bool = False  # set to true once AWS account is provisioned

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = json.loads(path.read_text())
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in known})
