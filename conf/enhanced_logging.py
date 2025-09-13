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

def detect_container_environment():
    """
    Detect if running in Docker, Kubernetes, or other container environments.
    
    Returns:
        dict: Environment detection results
    """
    env_info = {
        "is_docker": False,
        "is_kubernetes": False,
        "is_container": False,
        "pod_name": None,
        "namespace": None,
        "container_id": None,
        "platform": "host"
    }
    
    # Check for Docker
    if os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true':
        env_info["is_docker"] = True
        env_info["is_container"] = True
        env_info["platform"] = "docker"
    
    # Check for Kubernetes
    k8s_indicators = [
        os.environ.get('KUBERNETES_SERVICE_HOST'),
        os.path.exists('/var/run/secrets/kubernetes.io'),
        os.environ.get('KUBERNETES_PORT'),
        os.environ.get('POD_NAME'),
        os.environ.get('POD_NAMESPACE')
    ]
    
    if any(k8s_indicators):
        env_info["is_kubernetes"] = True
        env_info["is_container"] = True
        env_info["platform"] = "kubernetes"
        env_info["pod_name"] = os.environ.get('POD_NAME', hostname)
        env_info["namespace"] = os.environ.get('POD_NAMESPACE', 'default')
    
    # Get container ID if available
    try:
        if os.path.exists('/proc/self/cgroup'):
            with open('/proc/self/cgroup', 'r') as f:
                cgroup_content = f.read()
                # Extract container ID from cgroup
                for line in cgroup_content.split('\n'):
                    if 'docker' in line and len(line.split('/')) > 2:
                        container_id = line.split('/')[-1][:12]  # First 12 chars
                        env_info["container_id"] = container_id
                        break
    except Exception:
        pass
    
    return env_info

def get_structured_context():
    """
    Get structured context information for logging.
    
    Returns:
        dict: Structured context data
    """
    env_info = detect_container_environment()
    
    context = {
        "hostname": hostname,
        "app_name": app_name,
        "platform": env_info["platform"],
        "environment": {
            "is_container": env_info["is_container"],
            "is_docker": env_info["is_docker"],
            "is_kubernetes": env_info["is_kubernetes"]
        }
    }
    
    # Add Kubernetes-specific context
    if env_info["is_kubernetes"]:
        context["kubernetes"] = {
            "pod_name": env_info["pod_name"],
            "namespace": env_info["namespace"],
            "cluster": os.environ.get('CLUSTER_NAME', 'unknown'),
            "node": os.environ.get('NODE_NAME', 'unknown')
        }
    
    # Add Docker-specific context
    if env_info["is_docker"]:
        context["docker"] = {
            "container_id": env_info["container_id"],
            "image": os.environ.get('DOCKER_IMAGE', 'unknown')
        }
    
    # Add deployment context
    context["deployment"] = {
        "version": os.environ.get('APP_VERSION', 'unknown'),
        "commit": os.environ.get('GIT_COMMIT', 'unknown'),
        "build_date": os.environ.get('BUILD_DATE', 'unknown'),
        "environment": os.environ.get('ENVIRONMENT', 'development')
    }
    
    return context

def syslog_json_sink(message):
    """Enhanced syslog JSON sink with container-aware formatting."""
    record = message.record
    context = get_structured_context()
    
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

    # Get the process id if available
    procid = str(record["process"].id) if record.get("process") and hasattr(record["process"], "id") else "-"

    # Optionally, get a message ID from extra (or leave it as '-' if not provided)
    msgid = record["extra"].get("msgid", "-")

    # Get file and line details if available
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

    # Enhanced log record with container context
    log_record = {
        "pri": pri,
        "version": 1,
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "hostname": context["hostname"],
        "app_name": context["app_name"],
        "procid": procid,
        "msgid": msgid,
        "level": record["level"].name,
        "message": record["message"],
        "file": file_path,
        "line": line,
        "function": function,
        "context": context,
        "extra": extra_data if extra_data else None
    }
    
    # Add structured data for better parsing in log aggregators
    if context["environment"]["is_kubernetes"]:
        log_record["kubernetes"] = context.get("kubernetes", {})
    
    if context["environment"]["is_docker"]:
        log_record["docker"] = context.get("docker", {})
    
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
    Configure enhanced logging with container and Kubernetes awareness.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_file_logging: Whether to enable file logging (auto-disabled in K8s)
    """
    try:
        # Detect container environment
        env_info = detect_container_environment()
        context = get_structured_context()
        
        # Remove default loguru logger
        logger.remove()
        
        # Determine logging strategy based on environment
        use_structured_stdout = env_info["is_kubernetes"] or os.environ.get('LOG_FORMAT') == 'json'
        
        if use_structured_stdout:
            # Kubernetes/Container: Use structured JSON logging to stdout
            def k8s_json_sink(message):
                """Kubernetes-optimized JSON sink for stdout logging."""
                try:
                    record = message.record
                    
                    # Extract extra data safely
                    extra_data = {}
                    if "extra" in record and record["extra"]:
                        if "extra" in record["extra"]:
                            nested_extra = record["extra"]["extra"]
                            if isinstance(nested_extra, dict):
                                extra_data.update(nested_extra)
                        
                        for key, value in record["extra"].items():
                            if not key.startswith("_") and key not in ["extra", "logger_name"]:
                                extra_data[key] = str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
                    
                    # Kubernetes-optimized log entry
                    log_entry = {
                        "@timestamp": record["time"].isoformat(),
                        "level": record["level"].name,
                        "logger": record["name"],
                        "message": record["message"],
                        "context": context,
                        "source": {
                            "file": record["file"].path if "file" in record and record["file"] else None,
                            "line": record.get("line"),
                            "function": record.get("function")
                        },
                        "extra": extra_data if extra_data else None
                    }
                    
                    # Add trace information for debugging
                    if record.get("exception"):
                        log_entry["exception"] = str(record["exception"])
                    
                    print(json.dumps(log_entry, default=str))
                    
                except Exception as e:
                    # Fallback to simple format
                    print(f'{record["time"].isoformat()} | {record["level"].name} | {record["message"]}')
            
            logger.add(
                k8s_json_sink,
                level=log_level,
                backtrace=True,
                diagnose=True,
                catch=True
            )
            
            # Disable file logging in Kubernetes by default (use persistent volumes if needed)
            if env_info["is_kubernetes"]:
                enable_file_logging = enable_file_logging and os.environ.get('ENABLE_FILE_LOGGING') == 'true'
                
        else:
            # Development/Local: Use colorful console logging
            console_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )
            
            # Detect if colors should be disabled
            disable_colors = (
                env_info["is_container"] or 
                os.environ.get('NO_COLOR') == '1' or 
                os.environ.get('TERM') == 'dumb'
            )
            
            if disable_colors:
                console_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"
            
            logger.add(
                sys.stdout,
                format=console_format,
                level=log_level,
                colorize=not disable_colors,
                backtrace=True,
                diagnose=True,
                catch=True
            )
    
        # Add file logging if enabled (typically disabled in Kubernetes)
        if enable_file_logging:
            # Determine logs directory - use persistent volume in K8s if available
            if env_info["is_kubernetes"]:
                # Check for persistent volume mount
                logs_dir = Path(os.environ.get('LOG_VOLUME_PATH', '/app/logs'))
            else:
                logs_dir = ensure_logs_directory()
            
            # Ensure directory exists
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Main application log file (size-based rotation for better storage management)
            logger.add(
                logs_dir / "app_{time:YYYY-MM-DD_HH-mm}.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
                level=log_level,
                rotation="50 MB",
                retention="7 days",
                compression="gz",
                backtrace=True,
                diagnose=True
            )
            
            # Complete log file (all levels)
            logger.add(
                logs_dir / "complete_{time:YYYY-MM-DD}.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
                level=log_level,
                rotation="100 MB",
                retention="14 days",
                compression="gz",
                backtrace=True,
                diagnose=True
            )
            
            # Error-only log file
            logger.add(
                logs_dir / "errors_{time:YYYY-MM-DD}.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
                level="ERROR",
                rotation="50 MB",
                retention="90 days",
                compression="gz",
                backtrace=True,
                diagnose=True
            )
            
            # Container-aware JSON structured log
            def container_json_sink(message):
                """Container-optimized JSON sink with full context."""
                try:
                    record = message.record
                    
                    # Extract extra data safely
                    extra_data = {}
                    if "extra" in record and record["extra"]:
                        if "extra" in record["extra"]:
                            nested_extra = record["extra"]["extra"]
                            if isinstance(nested_extra, dict):
                                extra_data.update(nested_extra)
                        
                        for key, value in record["extra"].items():
                            if not key.startswith("_") and key not in ["extra", "logger_name"]:
                                extra_data[key] = str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
                    
                    # Full context log entry
                    log_entry = {
                        "@timestamp": record["time"].isoformat(),
                        "level": record["level"].name,
                        "logger": record["name"],
                        "message": record["message"],
                        "context": context,
                        "source": {
                            "file": record["file"].path if "file" in record and record["file"] else None,
                            "line": record.get("line"),
                            "function": record.get("function")
                        },
                        "extra": extra_data if extra_data else None
                    }
                    
                    # Write to structured log file
                    structured_log_path = logs_dir / f"structured_{record['time'].strftime('%Y-%m-%d_%H-%M')}.jsonl"
                    with open(structured_log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry, default=str) + "\n")
                        
                except Exception as e:
                    # Fallback logging
                    fallback_path = logs_dir / "structured_fallback.log"
                    with open(fallback_path, "a", encoding="utf-8") as f:
                        f.write(f'{record["time"].isoformat()} | {record["level"].name} | {record["message"]}\n')
            
            # Add container JSON sink
            logger.add(
                container_json_sink,
                level=log_level,
                filter=lambda record: True
            )
            
            # Performance/Access log with container context
            logger.add(
                logs_dir / "access_{time:YYYY-MM-DD}.log",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
                level="INFO",
                filter=lambda record: any(keyword in record["message"].lower() 
                                        for keyword in ["request", "response", "login", "logout", "webhook", "oauth"]),
                rotation="25 MB",
                retention="30 days",
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

        # Log configuration summary with environment context
        if enable_file_logging:
            log_stats = get_log_stats(logs_dir if 'logs_dir' in locals() else Path("logs"))
            logger.info("Enhanced logging configured with container awareness", extra={
                "log_level": log_level,
                "file_logging_enabled": enable_file_logging,
                "environment": context["environment"],
                "platform": context["platform"],
                "kubernetes": context.get("kubernetes") if env_info["is_kubernetes"] else None,
                "docker": context.get("docker") if env_info["is_docker"] else None,
                "logs_directory": str(logs_dir if 'logs_dir' in locals() else "disabled"),
                "existing_log_files": log_stats["total_files"],
                "existing_logs_size_mb": log_stats["total_size_mb"],
                "rotation_policy": {
                    "app_logs": "50MB rotation, 7 days retention",
                    "complete_logs": "100MB rotation, 14 days retention", 
                    "error_logs": "50MB rotation, 90 days retention",
                    "structured_logs": "Container-aware JSON format",
                },
                "compression": "gzip",
                "structured_format": use_structured_stdout
            })
        else:
            logger.info("Enhanced logging configured (console only) with container awareness", extra={
                "log_level": log_level,
                "file_logging_enabled": enable_file_logging,
                "environment": context["environment"],
                "platform": context["platform"],
                "structured_format": use_structured_stdout
            })
            
    except Exception as exc:
        # Fallback to basic logging if configuration fails
        print(f"Enhanced logging configuration failed: {exc}")
        print("Falling back to basic console logging...")
        logger.remove()
        logger.add(sys.stdout, level=log_level, format="{time} | {level} | {message}", colorize=False)


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
