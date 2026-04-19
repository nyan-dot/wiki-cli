from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from . import paths


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "event": getattr(record, "event_name", record.getMessage()),
        }

        command_name = getattr(record, "command_name", None)
        if command_name:
            payload["command"] = command_name

        record_payload = getattr(record, "payload", None)
        if isinstance(record_payload, dict):
            payload.update(record_payload)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


_ACTIVITY_LOGGER: logging.Logger | None = None
_ACTIVITY_LOGGER_PATH: Path | None = None


def get_activity_logger() -> logging.Logger:
    global _ACTIVITY_LOGGER
    global _ACTIVITY_LOGGER_PATH

    current_path = paths.activity_log_path().resolve()
    if _ACTIVITY_LOGGER is not None and current_path == _ACTIVITY_LOGGER_PATH:
        return _ACTIVITY_LOGGER

    paths.log_root().mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("wiki.activity")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(current_path, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)

    _ACTIVITY_LOGGER = logger
    _ACTIVITY_LOGGER_PATH = current_path
    return logger


def serialize_log_value(value: object) -> object:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): serialize_log_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_log_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def log_activity(
    event_name: str,
    *,
    level: int = logging.INFO,
    command_name: str | None = None,
    exc_info: object = None,
    **payload: object,
) -> None:
    logger = get_activity_logger()
    logger.log(
        level,
        event_name,
        exc_info=exc_info,
        extra={
            "event_name": event_name,
            "command_name": command_name,
            "payload": serialize_log_value(payload),
        },
    )


def command_arguments(args: argparse.Namespace) -> dict[str, object]:
    return {
        key: serialize_log_value(value)
        for key, value in vars(args).items()
        if key != "func"
    }
