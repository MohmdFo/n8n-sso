import sys
import json
import socket
import os
import logging
import time
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
    """Ensure logs directory exists and clean up old logs if needed."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Clean up old log files beyond retention policy (safety cleanup)
    cleanup_old_logs(logs_dir)
    
    return logs_dir


def cleanup_old_logs(logs_dir: Path, max_total_size_mb: int = 1024):
    """
    Clean up old log files if total size exceeds limit.
    
    Args:
        logs_dir: Path to logs directory
        max_total_size_mb: Maximum total size of all logs in MB (default: 1GB)
    """
    try:
        import time
        from pathlib import Path
        
        # Get all log files with their sizes and modification times
        log_files = []
        total_size = 0
        
        for log_file in logs_dir.glob("*.log*"):
            if log_file.is_file():
                size = log_file.stat().st_size
                mtime = log_file.stat().st_mtime
                total_size += size
                log_files.append((log_file, size, mtime))
        
        # Convert MB to bytes
        max_total_size_bytes = max_total_size_mb * 1024 * 1024
        
        if total_size > max_total_size_bytes:
            # Sort by modification time (oldest first)
            log_files.sort(key=lambda x: x[2])
            
            # Remove oldest files until under limit
            for log_file, size, _ in log_files:
                if total_size <= max_total_size_bytes:
                    break
                
                try:
                    log_file.unlink()
                    total_size -= size
                    print(f"Cleaned up old log file: {log_file.name} ({size / 1024 / 1024:.2f} MB)")
                except Exception as e:
                    print(f"Failed to clean up {log_file.name}: {e}")
                    
    except Exception as e:
        print(f"Log cleanup failed: {e}")


def get_log_stats(logs_dir: Path = None):
    """Get statistics about log files."""
    if logs_dir is None:
        logs_dir = Path("logs")
    
    if not logs_dir.exists():
        return {"total_files": 0, "total_size_mb": 0}
    
    total_size = 0
    file_count = 0
    
    for log_file in logs_dir.glob("*.log*"):
        if log_file.is_file():
            total_size += log_file.stat().st_size
            file_count += 1
    
    return {
        "total_files": file_count,
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "directory": str(logs_dir)
    }


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
        
        # Main application log file (size-based rotation for better storage management)
        logger.add(
            logs_dir / "app_{time:YYYY-MM-DD_HH-mm}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation="50 MB",  # Rotate when file reaches 50MB
            retention="7 days",  # Keep app logs for 1 week (shorter since we have complete logs)
            compression="gz",  # Use gzip compression
            backtrace=True,
            diagnose=True
        )
        
        # Complete log file (all levels) - separate from daily app logs for better management
        logger.add(
            logs_dir / "complete_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
            level=log_level,  # Log everything from the configured level
            rotation="100 MB",  # Rotate when file reaches 100MB
            retention="14 days",  # Keep complete logs for 2 weeks
            compression="gz",  # Use gzip compression (better than zip for text)
            backtrace=True,
            diagnose=True
        )
        
        # Error-only log file (ERROR and CRITICAL only)
        logger.add(
            logs_dir / "errors_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
            level="ERROR",
            rotation="50 MB",  # Smaller rotation for error logs
            retention="90 days",  # Keep error logs longer for debugging
            compression="gz",
            backtrace=True,
            diagnose=True
        )
        
        # JSON structured log for parsing/monitoring (optimized rotation)
        logger.add(
            logs_dir / "structured_{time:YYYY-MM-DD_HH-mm}.jsonl",
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
            rotation="75 MB",  # Larger rotation for JSON (more verbose)
            retention="21 days",  # Keep structured logs for 3 weeks
            compression="gz"
        )
        
        # Performance/Access log (INFO and above, for monitoring)
        logger.add(
            logs_dir / "access_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
            level="INFO",
            filter=lambda record: any(keyword in record["message"].lower() 
                                    for keyword in ["request", "response", "login", "logout", "webhook", "oauth"]),
            rotation="25 MB",
            retention="30 days",  # Keep access logs for monitoring
            compression="gz"
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

    # Log configuration summary
    if enable_file_logging:
        log_stats = get_log_stats(logs_dir)
        logger.info("Enhanced logging configured with file rotation and cleanup", extra={
            "log_level": log_level,
            "file_logging_enabled": enable_file_logging,
            "logs_directory": str(logs_dir),
            "existing_log_files": log_stats["total_files"],
            "existing_logs_size_mb": log_stats["total_size_mb"],
            "rotation_policy": {
                "app_logs": "50MB rotation, 7 days retention",
                "complete_logs": "100MB rotation, 14 days retention", 
                "error_logs": "50MB rotation, 90 days retention",
                "structured_logs": "75MB rotation, 21 days retention",
                "access_logs": "25MB rotation, 30 days retention"
            },
            "compression": "gzip",
            "max_total_size": "1GB (auto-cleanup)"
        })
    else:
        logger.info("Enhanced logging configured (console only)", extra={
            "log_level": log_level,
            "file_logging_enabled": enable_file_logging
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


def monitor_log_health():
    """Monitor log file health and report issues."""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return {"status": "no_logs_directory"}
    
    stats = get_log_stats(logs_dir)
    health_status = {
        "status": "healthy",
        "stats": stats,
        "warnings": []
    }
    
    # Check for potential issues
    if stats["total_size_mb"] > 800:  # 80% of 1GB limit
        health_status["warnings"].append(f"Log directory size approaching limit: {stats['total_size_mb']} MB")
        health_status["status"] = "warning"
    
    if stats["total_files"] > 100:
        health_status["warnings"].append(f"Many log files present: {stats['total_files']} files")
        health_status["status"] = "warning"
    
    # Check if logs are being written (check most recent file)
    recent_logs = sorted(logs_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if recent_logs:
        latest_log = recent_logs[0]
        age_hours = (time.time() - latest_log.stat().st_mtime) / 3600
        if age_hours > 1:  # No logs in last hour
            health_status["warnings"].append(f"Latest log file is {age_hours:.1f} hours old")
            if age_hours > 24:
                health_status["status"] = "error"
    else:
        health_status["warnings"].append("No log files found")
        health_status["status"] = "error"
    
    return health_status
