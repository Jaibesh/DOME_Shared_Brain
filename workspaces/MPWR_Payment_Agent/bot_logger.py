"""
bot_logger.py — Structured Logging for MPWR Payment Agent

Provides a dual-output logger that writes:
  1. Rich human-readable output to console (stdout)
  2. Structured JSON-lines to a rotating log file
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "ctx") and isinstance(record.ctx, dict):
            log_entry["context"] = record.ctx
        return json.dumps(log_entry, ensure_ascii=False)

class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()

def get_bot_logger(name: str = "mpowr_payment_agent") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    if hasattr(console_handler.stream, "reconfigure"):
        console_handler.stream.reconfigure(encoding="utf-8")
    logger.addHandler(console_handler)

    log_file = os.path.join(LOG_DIR, "mpowr_payment_agent.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    logger.info(f"Logger initialized. File: {log_file}")
    return logger
