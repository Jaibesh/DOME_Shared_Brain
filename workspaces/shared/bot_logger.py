"""
bot_logger.py — Unified Structured Logging for All DOME Agents

Provides a dual-output logger that writes:
  1. Rich human-readable output to console (stdout)
  2. Structured JSON-lines to a rotating log file

Each log entry includes the agent_id for cross-agent log correlation.

Usage:
    from shared.bot_logger import get_bot_logger
    log = get_bot_logger("mpwr_creator")
    log.info("Reservation created", extra={"ctx": {"tw_conf": "CO-123"}})
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON-lines for machine parsing and cross-agent correlation."""

    def __init__(self, agent_id: str = "unknown"):
        super().__init__()
        self.agent_id = agent_id

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "agent_id": self.agent_id,
            "message": record.getMessage(),
        }
        # Attach extra context fields (tw_confirmation, activity, etc.)
        if hasattr(record, "ctx") and isinstance(record.ctx, dict):
            log_entry["context"] = record.ctx
        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Rich console formatter with agent prefix for multi-agent environments."""

    def __init__(self, agent_id: str = ""):
        super().__init__()
        self.prefix = f"[{agent_id}] " if agent_id else ""

    def format(self, record: logging.LogRecord) -> str:
        return f"{self.prefix}{record.getMessage()}"


def get_bot_logger(agent_name: str = "dome_agent", log_dir: str = None) -> logging.Logger:
    """
    Creates (or retrieves) a structured logger for the given agent.

    Returns a logger with two handlers:
      - Console: human-readable with agent prefix (INFO+)
      - File: JSON-lines in logs/<agent_name>.log (rotates daily at midnight, 30 backups)

    Args:
        agent_name: Unique identifier for this agent (used in log filename and JSON entries)
        log_dir: Override log directory. Defaults to <caller_dir>/logs/

    Usage:
        from shared.bot_logger import get_bot_logger
        log = get_bot_logger("mpwr_creator")
        log.info("Step completed", extra={"ctx": {"tw_conf": "CO-123"}})
    """
    logger = logging.getLogger(agent_name)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # --- Console handler (INFO+) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter(agent_id=agent_name))
    # Force UTF-8 encoding on Windows
    if hasattr(console_handler.stream, "reconfigure"):
        console_handler.stream.reconfigure(encoding="utf-8")
    logger.addHandler(console_handler)

    # --- File handler (DEBUG+, JSON-lines, timed rotation) ---
    if log_dir is None:
        # Default: logs/ directory relative to the calling agent's directory
        import inspect
        caller_dir = os.path.dirname(os.path.abspath(inspect.stack()[1].filename))
        log_dir = os.path.join(caller_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{agent_name}.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter(agent_id=agent_name))
    logger.addHandler(file_handler)

    logger.info(f"Logger initialized. File: {log_file}")
    return logger
