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
    function = record.get("function", "-")

    # Include extra data from the log record
    extra_data = {}
    if record.get("extra"):
        # Filter out internal loguru fields and include user-provided extras
        for key, value in record["extra"].items():
            if not key.startswith("_"):
                extra_data[key] = value

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
        "file": file_path,
        "line": line,
        "function": function,
        "extra": extra_data if extra_data else None
    }
    sys.stdout.write(json.dumps(log_record, default=str) + "\n")


def ensure_logs_directory():
    """Ensure logs directory exists."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


def configure_enhanced_logging(log_level="INFO", enable_file_logging=True):
    """
    Configure enhanced logging with both console and file output.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_file_logging: Whether to enable file logging in addition to console
    """
    # Remove default loguru logger
    logger.remove()
    
    # Console output - colorful format for development
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Add console logging (always enabled)
    logger.add(
        sys.stdout,
        format=console_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # Add file logging if enabled
    if enable_file_logging:
        logs_dir = ensure_logs_directory()
        
        # Main application log file (rotated daily)
        logger.add(
            logs_dir / "app_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation="00:00",  # Rotate at midnight
            retention="30 days",  # Keep logs for 30 days
            compression="zip",  # Compress old logs
            backtrace=True,
            diagnose=True
        )
        
        # Error-only log file
        logger.add(
            logs_dir / "errors_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level="ERROR",
            rotation="00:00",
            retention="90 days",  # Keep error logs longer
            compression="zip",
            backtrace=True,
            diagnose=True
        )
        
        # JSON structured log for parsing/monitoring
        logger.add(
            logs_dir / "structured_{time:YYYY-MM-DD}.jsonl",
            format=lambda record: json.dumps({
                "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "level": record["level"].name,
                "logger": record["name"],
                "file": record["file"].path if record.get("file") else None,
                "line": record.get("line"),
                "function": record.get("function"),
                "message": record["message"],
                "extra": {k: v for k, v in record.get("extra", {}).items() if not k.startswith("_")}
            }, default=str) + "\n",
            level=log_level,
            rotation="00:00",
            retention="30 days",
            compression="zip"
        )
    
    # Bridge loguru with standard library logging
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            # Get corresponding Loguru level if it exists
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    # Intercept standard library logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Configure third-party loggers
    for logger_name in ["uvicorn", "fastapi", "httpx", "sqlalchemy.engine"]:
        logging.getLogger(logger_name).handlers = [InterceptHandler()]
        logging.getLogger(logger_name).propagate = False

    logger.info("Enhanced logging configured", extra={
        "log_level": log_level,
        "file_logging_enabled": enable_file_logging,
        "logs_directory": str(logs_dir) if enable_file_logging else None
    })


def configure_syslog_stdout(log_level="INFO"):
    """
    Configures Loguru to output JSON syslog-formatted logs to stdout via a custom sink.
    This is kept for backward compatibility.
    """
    logger.remove()
    logger.add(syslog_json_sink, level=log_level, colorize=False)


def get_logger(name: str = None):
    """
    Get a logger instance with optional name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Loguru logger instance
    """
    if name:
        return logger.bind(logger_name=name)
    return logger
