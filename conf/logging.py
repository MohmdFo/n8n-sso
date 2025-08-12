import sys
import json
import socket
from loguru import logger

hostname = socket.gethostname()
app_name = "gateway"

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
    function = record.get("function", "-")

    log_record = {
        "pri": pri,
        "version": 1,
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "hostname": hostname,
        "app_name": app_name,
        "procid": procid,
        "msgid": msgid,
        "level": record["level"].name,
        "message": record["message"],
    }
    sys.stdout.write(json.dumps(log_record) + "\n")

def configure_syslog_stdout(log_level="INFO"):
    """
    Configures Loguru to output JSON syslog-formatted logs to stdout via a custom sink.
    """
    logger.remove()
    logger.add(syslog_json_sink, level=log_level, colorize=False)
