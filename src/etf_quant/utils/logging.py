from __future__ import annotations

import logging
import os
from typing import Final

CREDENTIAL_ENV_NAMES: Final[tuple[str, ...]] = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)


def redact_secrets(text: str) -> str:
    redacted = text
    for name in CREDENTIAL_ENV_NAMES:
        value = os.getenv(name)
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


class CredentialRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        record.msg = redact_secrets(rendered)
        record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(item, CredentialRedactionFilter) for item in logger.filters):
        logger.addFilter(CredentialRedactionFilter())
    return logger

