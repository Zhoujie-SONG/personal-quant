from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, TypeVar

from etf_quant.providers.longbridge.exceptions import (
    LongbridgeAuthenticationError,
    LongbridgeProviderError,
    translate_longbridge_error,
)
from etf_quant.utils.logging import CREDENTIAL_ENV_NAMES, get_logger

T = TypeVar("T")
logger = get_logger(__name__)


class LongbridgeClient:
    """Small retrying wrapper around a QuoteContext.

    The SDK Config and credentials are never retained as public attributes, and
    credentials are read only by Config.from_apikey_env().
    """

    def __init__(
        self,
        quote_context: Any,
        *,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.5,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._quote_context = quote_context
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds

    @classmethod
    def from_env(
        cls,
        *,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.5,
    ) -> "LongbridgeClient":
        missing = [name for name in CREDENTIAL_ENV_NAMES if not os.getenv(name)]
        if missing:
            raise LongbridgeAuthenticationError(
                "missing required Longbridge environment variables: " + ", ".join(missing),
                operation="create_client",
            )
        try:
            from longbridge.openapi import Config, QuoteContext

            context = QuoteContext(Config.from_apikey_env())
        except Exception as exc:
            raise translate_longbridge_error(exc, "create_client") from exc
        return cls(
            context,
            max_attempts=max_attempts,
            retry_base_seconds=retry_base_seconds,
        )

    def query(self, operation: str, call: Callable[[Any], T]) -> T:
        last_error: LongbridgeProviderError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return call(self._quote_context)
            except LongbridgeProviderError:
                raise
            except Exception as exc:
                error = translate_longbridge_error(exc, operation)
                last_error = error
                if not error.retryable or attempt == self._max_attempts:
                    raise error from exc
                delay = self._retry_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Longbridge query %s failed on attempt %d/%d; retrying in %.2fs: %s",
                    operation,
                    attempt,
                    self._max_attempts,
                    delay,
                    error,
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def __repr__(self) -> str:
        return (
            f"LongbridgeClient(max_attempts={self._max_attempts}, "
            f"retry_base_seconds={self._retry_base_seconds})"
        )

