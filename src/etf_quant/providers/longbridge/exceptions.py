from __future__ import annotations

from etf_quant.utils.logging import redact_secrets


class LongbridgeProviderError(RuntimeError):
    def __init__(self, message: str, *, operation: str, retryable: bool = False) -> None:
        super().__init__(redact_secrets(message))
        self.operation = operation
        self.retryable = retryable


class LongbridgePermissionError(LongbridgeProviderError):
    pass


class LongbridgeAuthenticationError(LongbridgeProviderError):
    pass


class LongbridgeDataError(LongbridgeProviderError):
    pass


def translate_longbridge_error(exc: Exception, operation: str) -> LongbridgeProviderError:
    message = redact_secrets(str(exc))
    lowered = message.lower()
    if any(token in lowered for token in ("301604", "no access", "no permission", "permission limit")):
        return LongbridgePermissionError(message, operation=operation)
    if any(
        token in lowered
        for token in (
            "unauthorized", "authentication", "invalid token", "token invalid",
            "token expired", "401003", "401004", "app key",
        )
    ):
        return LongbridgeAuthenticationError(message, operation=operation)
    retryable = any(
        token in lowered
        for token in ("301606", "301602", "rate limit", "timeout", "temporarily", "connection")
    )
    return LongbridgeProviderError(message, operation=operation, retryable=retryable)
