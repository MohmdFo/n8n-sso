import sys
import json
import socket
import os
import logging
from datetime import datetime
from pathlib import Path
from loguru import logger

hostname = socket.gethostname()
app_name = "n8n-sso-gateway"

def syslog_json_sink(message):
    record = message.record  # Loguru's record dictionary
    level_to_severity = {
        "TRACE": 7,
        "DEBUG": 7,
        "INFO": 6,
        "SUCCESS": 5,
        "WARNING": 4,
        "ERROR": 3,
        "CRITICAL": 2,
    }
    severity = level_to_severity.get(record["level"].name, 6)
    facility = 1  # adjust as needed
    pri = facility * 8 + severity

    # Get the process id if available.
    procid = str(record["process"].id) if record.get("process") and hasattr(record["process"], "id") else "-"

    # Optionally, get a message ID from extra (or leave it as '-' if not provided)
    msgid = record["extra"].get("msgid", "-")

    # Get file and line details if available.
    file_path = record["file"].path if record.get("file") else "-"
    line = record.get("line", "-")
