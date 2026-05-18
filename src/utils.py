import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Config

IST = ZoneInfo("Asia/Kolkata")


def setup_logging(log_file: str) -> logging.Logger:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("FileSyncAgent")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def within_schedule_window(config: Config) -> bool:
    now = datetime.now(IST).time()
    start = datetime.strptime(config.schedule_window_start_ist, "%H:%M").time()
    end = datetime.strptime(config.schedule_window_end_ist, "%H:%M").time()
    return start <= now <= end
