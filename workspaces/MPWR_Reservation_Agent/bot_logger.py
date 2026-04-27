"""
bot_logger.py — Structured Logging for MPOWR Creator Bot

Provides a dual-output logger that writes:
  1. Rich human-readable output to console (stdout)
  2. Structured JSON-lines to a rotating log file

ARCH-3 FIX: Uses TimedRotatingFileHandler instead of RotatingFileHandler
to properly rotate by date at midnight. Previous implementation embedded
today's date in the filename at startup, which meant logs from after midnight
went to yesterday's file until the process restarted.

Log files are stored in backend/logs/ and rotate daily, keeping 30 backups.
Each log entry contains: timestamp, level, message, and optional context fields.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

# ---------------------------------------------------------------------------
# Log directory setup
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON-lines for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            # LOW-2 FIX: utcfromtimestamp() is deprecated in Python 3.12+
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        # Attach extra context fields (tw_confirmation, activity, etc.)
        if hasattr(record, "ctx") and isinstance(record.ctx, dict):
            log_entry["context"] = record.ctx
        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Rich console formatter that preserves the emoji-based print() style."""

    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def get_bot_logger(name: str = "mpowr_bot") -> logging.Logger:
    """
    Creates (or retrieves) the singleton bot logger.

    Returns a logger with two handlers:
      - Console: human-readable, same style as existing print() output
      - File: JSON-lines in logs/mpowr_bot.log (rotates daily at midnight, 30 backups)

    ARCH-3 FIX: Uses TimedRotatingFileHandler which rotates at midnight
    regardless of process uptime. Old files get suffixed with the date
    (e.g., mpowr_bot.log.2026-04-12).

    Usage:
        from bot_logger import get_bot_logger
        log = get_bot_logger()
        log.info("Step completed", extra={"ctx": {"tw_conf": "CO-123"}})
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # --- Console handler (INFO+) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    # Force UTF-8 encoding on Windows
    if hasattr(console_handler.stream, "reconfigure"):
        console_handler.stream.reconfigure(encoding="utf-8")
    logger.addHandler(console_handler)

    # --- File handler (DEBUG+, JSON-lines, timed rotation) ---
    # ARCH-3: TimedRotatingFileHandler rotates at midnight automatically.
    # No need to embed date in filename — the handler adds date suffixes.
    log_file = os.path.join(LOG_DIR, "mpowr_bot.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",       # Rotate at midnight
        interval=1,            # Every 1 day
        backupCount=30,        # Keep 30 days of history
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"   # Rotated files: mpowr_bot.log.2026-04-12
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    logger.info(f"Logger initialized. File: {log_file}")
    return logger
