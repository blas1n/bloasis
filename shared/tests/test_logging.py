"""
Unit tests for the logging utility module.

Tests cover JSONFormatter and setup_logger functionality.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import patch

import pytest

from shared.utils.logging import JSONFormatter, setup_logger


class TestJSONFormatter:
    """Tests for the JSONFormatter class."""

    def test_init_sets_service_name(self) -> None:
        """Test that __init__ correctly sets the service name."""
        formatter = JSONFormatter(service_name="test-service")
        assert formatter.service_name == "test-service"

    def test_format_produces_valid_json(self) -> None:
        """Test that format() outputs valid JSON."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        # Should be valid JSON
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_format_includes_timestamp(self) -> None:
        """Test that format() includes ISO 8601 timestamp."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "timestamp" in parsed
        # Verify ISO 8601 format with Z suffix
        assert parsed["timestamp"].endswith("Z")
        # Should have milliseconds
        assert "." in parsed["timestamp"]

    def test_format_includes_service_name(self) -> None:
        """Test that format() includes the service name."""
        formatter = JSONFormatter(service_name="market-regime")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["service"] == "market-regime"

    def test_format_includes_level(self) -> None:
        """Test that format() includes the log level."""
        formatter = JSONFormatter(service_name="test-service")

        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level, level_name in levels:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )

            output = formatter.format(record)
            parsed = json.loads(output)

            assert parsed["level"] == level_name

    def test_format_includes_message(self) -> None:
        """Test that format() includes the log message."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Processing request for user %s",
            args=("user123",),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == "Processing request for user user123"

    def test_format_includes_extra_fields(self) -> None:
        """Test that format() includes extra fields from logger.info(..., extra={})."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Add extra fields
        record.user_id = "abc123"
        record.request_id = "req-456"
        record.latency_ms = 150

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["user_id"] == "abc123"
        assert parsed["request_id"] == "req-456"
        assert parsed["latency_ms"] == 150

    def test_format_excludes_reserved_attrs(self) -> None:
        """Test that reserved LogRecord attributes are not included as extra fields."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        # These should not be in the output
        reserved = ["name", "pathname", "lineno", "funcName", "module"]
        for attr in reserved:
            assert attr not in parsed

    def test_format_handles_exception_in_extra(self) -> None:
        """Test that exceptions in extra fields are serialized as strings."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=None,
        )

        record.error = ValueError("Invalid value")

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["error"] == "Invalid value"

    def test_format_handles_complex_types(self) -> None:
        """Test that complex types in extra fields are handled correctly."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        record.data = {"key": "value", "nested": {"a": 1}}
        record.items = [1, 2, 3]

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["data"] == {"key": "value", "nested": {"a": 1}}
        assert parsed["items"] == [1, 2, 3]

    def test_format_timestamp_utc(self) -> None:
        """Test that timestamp is in UTC."""
        formatter = JSONFormatter(service_name="test-service")

        # Use a known timestamp: 2024-01-29T11:50:00.123Z UTC
        known_time = 1706529000.123

        timestamp_str = formatter._format_timestamp(known_time)

        # Should end with Z (UTC indicator)
        assert timestamp_str.endswith("Z")
        # Parse and verify
        assert "2024-01-29T11:50:00.123Z" == timestamp_str


class TestSetupLogger:
    """Tests for the setup_logger function."""

    def teardown_method(self) -> None:
        """Clean up loggers after each test."""
        # Remove any test loggers to prevent interference
        for name in list(logging.Logger.manager.loggerDict.keys()):
            if name.startswith("test-"):
                logger = logging.getLogger(name)
                logger.handlers.clear()

    def test_returns_logger_instance(self) -> None:
        """Test that setup_logger returns a logging.Logger instance."""
        logger = setup_logger("test-service-1")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_correct_name(self) -> None:
        """Test that the logger has the correct name."""
        logger = setup_logger("test-service-2")
        assert logger.name == "test-service-2"

    def test_logger_has_json_formatter(self) -> None:
        """Test that the logger uses JSONFormatter."""
        logger = setup_logger("test-service-3")

        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)

    def test_logger_uses_stream_handler(self) -> None:
        """Test that the logger uses StreamHandler for stdout."""
        logger = setup_logger("test-service-4")

        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)

    def test_explicit_level_parameter(self) -> None:
        """Test that explicit level parameter is used."""
        logger = setup_logger("test-service-5", level="DEBUG")
        assert logger.level == logging.DEBUG

        logger2 = setup_logger("test-service-6", level="WARNING")
        assert logger2.level == logging.WARNING

    def test_level_from_env_variable(self) -> None:
        """Test that LOG_LEVEL environment variable is used."""
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            logger = setup_logger("test-service-7")
            assert logger.level == logging.ERROR

    def test_default_level_is_info(self) -> None:
        """Test that default level is INFO when LOG_LEVEL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure LOG_LEVEL is not set
            os.environ.pop("LOG_LEVEL", None)
            logger = setup_logger("test-service-8")
            assert logger.level == logging.INFO

    def test_explicit_level_overrides_env(self) -> None:
        """Test that explicit level parameter overrides LOG_LEVEL env var."""
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            logger = setup_logger("test-service-9", level="DEBUG")
            assert logger.level == logging.DEBUG

    def test_level_case_insensitive(self) -> None:
        """Test that level parameter is case insensitive."""
        logger1 = setup_logger("test-service-10", level="debug")
        assert logger1.level == logging.DEBUG

        logger2 = setup_logger("test-service-11", level="DEBUG")
        assert logger2.level == logging.DEBUG

        logger3 = setup_logger("test-service-12", level="Debug")
        assert logger3.level == logging.DEBUG

    def test_no_propagation(self) -> None:
        """Test that logger does not propagate to root logger."""
        logger = setup_logger("test-service-13")
        assert logger.propagate is False

    def test_clears_existing_handlers(self) -> None:
        """Test that existing handlers are cleared to prevent duplicates."""
        # Set up logger twice
        logger1 = setup_logger("test-service-14")
        logger2 = setup_logger("test-service-14")  # Same name

        # Should have only one handler
        assert len(logger2.handlers) == 1


class TestJSONFormatterIntegration:
    """Integration tests for JSONFormatter with actual logging."""

    def test_logger_produces_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that logger output is valid JSON."""
        logger = setup_logger("integration-test-1")

        # Log a message
        logger.info("Test message")

        # Capture output
        captured = capsys.readouterr()

        # Should be valid JSON
        output_line = captured.err.strip()  # StreamHandler writes to stderr by default
        parsed = json.loads(output_line)

        assert parsed["service"] == "integration-test-1"
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"

    def test_logger_with_extra_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that extra fields are included in JSON output."""
        logger = setup_logger("integration-test-2")

        # Log with extra fields
        logger.info("Processing request", extra={"user_id": "abc123", "action": "login"})

        # Capture output
        captured = capsys.readouterr()
        output_line = captured.err.strip()
        parsed = json.loads(output_line)

        assert parsed["user_id"] == "abc123"
        assert parsed["action"] == "login"

    def test_logger_respects_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that logger respects the configured level."""
        logger = setup_logger("integration-test-3", level="WARNING")

        # This should not be logged
        logger.info("Info message")

        # This should be logged
        logger.warning("Warning message")

        # Capture output
        captured = capsys.readouterr()

        # Only warning should be present
        assert "Warning message" in captured.err
        assert "Info message" not in captured.err


class TestJSONFormatterEdgeCases:
    """Edge case tests for JSONFormatter."""

    def test_empty_message(self) -> None:
        """Test formatting with empty message."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == ""

    def test_unicode_message(self) -> None:
        """Test formatting with unicode characters."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test with unicode: \u4e2d\u6587 \u65e5\u672c\u8a9e \ud55c\uad6d\uc5b4",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "Test with unicode:" in parsed["message"]

    def test_special_characters_in_message(self) -> None:
        """Test formatting with special JSON characters."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Message with "quotes" and \\backslash',
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        # Should be valid JSON
        parsed = json.loads(output)

        assert '"quotes"' in parsed["message"]
        assert "\\backslash" in parsed["message"]

    def test_none_value_in_extra(self) -> None:
        """Test handling None values in extra fields."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        record.optional_field = None

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["optional_field"] is None

    def test_boolean_values_in_extra(self) -> None:
        """Test handling boolean values in extra fields."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        record.is_valid = True
        record.is_cached = False

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["is_valid"] is True
        assert parsed["is_cached"] is False

    def test_numeric_values_in_extra(self) -> None:
        """Test handling various numeric values in extra fields."""
        formatter = JSONFormatter(service_name="test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        record.count = 42
        record.ratio = 3.14159
        record.big_number = 1000000000

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["count"] == 42
        assert parsed["ratio"] == 3.14159
        assert parsed["big_number"] == 1000000000
