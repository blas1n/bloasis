"""
Structured JSON logging utility for BLOASIS services.

Provides consistent, machine-readable logging across all microservices
with support for structured fields and contextual information.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Custom logging formatter that outputs logs in JSON format.

    Produces structured JSON logs with consistent fields:
    - timestamp: ISO 8601 formatted UTC timestamp
    - service: Name of the service producing the log
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - message: The log message
    - Additional fields from the 'extra' parameter

    Example output:
        {
            "timestamp": "2026-01-29T12:30:00.000Z",
            "service": "market-regime",
            "level": "INFO",
            "message": "Processing request",
            "user_id": "abc123"
        }

    Example:
        >>> formatter = JSONFormatter(service_name="market-regime")
        >>> handler = logging.StreamHandler()
        >>> handler.setFormatter(formatter)
        >>> logger = logging.getLogger("my_logger")
        >>> logger.addHandler(handler)
        >>> logger.info("Request received", extra={"user_id": "abc123"})
    """

    # Standard LogRecord attributes to exclude from extra fields
    _RESERVED_ATTRS = frozenset({
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs",
        "pathname", "process", "processName", "relativeCreated",
        "stack_info", "exc_info", "exc_text", "thread", "threadName",
        "taskName", "message",
    })

    def __init__(self, service_name: str) -> None:
        """
        Initialize the JSON formatter.

        Args:
            service_name: The name of the service to include in all log entries.
                         This should be consistent across all logs from a service.

        Example:
            >>> formatter = JSONFormatter(service_name="market-regime")
        """
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as a JSON string.

        Constructs a JSON object with standard fields (timestamp, service,
        level, message) and any additional fields passed via the 'extra'
        parameter in the logging call.

        Args:
            record: The log record to format.

        Returns:
            A JSON-formatted string representing the log entry.

        Example:
            >>> # When logger.info("Hello", extra={"user_id": "123"}) is called:
            >>> # Returns: '{"timestamp": "...", "service": "...", "level": "INFO",
            >>> #           "message": "Hello", "user_id": "123"}'
        """
        # Build base log entry with required fields
        log_entry: Dict[str, Any] = {
            "timestamp": self._format_timestamp(record.created),
            "service": self.service_name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Add extra fields from the log record
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS and not key.startswith("_"):
                log_entry[key] = self._serialize_value(value)

        return json.dumps(log_entry, ensure_ascii=False)

    def _format_timestamp(self, created: float) -> str:
        """
        Format a timestamp as ISO 8601 string in UTC.

        Args:
            created: Unix timestamp (seconds since epoch).

        Returns:
            ISO 8601 formatted timestamp string with 'Z' suffix.

        Example:
            >>> formatter = JSONFormatter(service_name="test")
            >>> formatter._format_timestamp(1706529000.0)
            '2024-01-29T12:30:00.000Z'
        """
        dt = datetime.fromtimestamp(created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}Z"

    def _serialize_value(self, value: Any) -> Any:
        """
        Serialize a value for JSON output.

        Handles special cases like exceptions and objects that are not
        directly JSON serializable.

        Args:
            value: The value to serialize.

        Returns:
            A JSON-serializable representation of the value.
        """
        if isinstance(value, Exception):
            return str(value)
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (list, dict)):
            return value
        # For other types, convert to string
        return str(value)


def setup_logger(
    service_name: str,
    level: Optional[str] = None,
) -> logging.Logger:
    """
    Set up and return a configured logger with JSON formatting.

    Creates a logger that outputs structured JSON logs to stdout.
    The log level can be configured via the 'level' parameter or
    the LOG_LEVEL environment variable.

    Args:
        service_name: The name of the service. This will be included
                     in every log entry's 'service' field.
        level: The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If not provided, reads from LOG_LEVEL environment variable.
               Defaults to INFO if neither is set.

    Returns:
        A configured logging.Logger instance with JSON formatting.

    Example:
        >>> import os
        >>> os.environ["LOG_LEVEL"] = "DEBUG"
        >>> logger = setup_logger("market-regime")
        >>> logger.info("Processing request", extra={"user_id": "abc123"})
        {"timestamp": "2026-01-29T12:30:00.000Z", "service": "market-regime",
         "level": "INFO", "message": "Processing request", "user_id": "abc123"}

    Example with explicit level:
        >>> logger = setup_logger("notification-service", level="WARNING")
        >>> logger.warning("High latency detected", extra={"latency_ms": 500})
        {"timestamp": "...", "service": "notification-service",
         "level": "WARNING", "message": "High latency detected", "latency_ms": 500}

    Note:
        - The logger uses a StreamHandler to write to stdout
        - Existing handlers are removed to prevent duplicate logs
        - Log propagation is disabled to prevent duplicate logs from root logger
    """
    # Determine log level
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")

    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger with service name
    logger = logging.getLogger(service_name)
    logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create stream handler for stdout
    handler = logging.StreamHandler()
    handler.setLevel(numeric_level)

    # Apply JSON formatter
    formatter = JSONFormatter(service_name=service_name)
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False

    return logger
