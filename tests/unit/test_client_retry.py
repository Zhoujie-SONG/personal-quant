from __future__ import annotations

import pytest

from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.exceptions import LongbridgePermissionError, LongbridgeProviderError


def test_safe_transient_query_is_retried(monkeypatch) -> None:
    attempts = 0

    def operation(_: object) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("301606 rate limit")
        return "ok"

    monkeypatch.setattr("etf_quant.providers.longbridge.client.time.sleep", lambda _: None)
    client = LongbridgeClient(object(), max_attempts=3, retry_base_seconds=0)
    assert client.query("quote", operation) == "ok"
    assert attempts == 3


def test_permission_error_is_wrapped_and_not_retried() -> None:
    attempts = 0

    def operation(_: object) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("301604 No access")

    client = LongbridgeClient(object(), max_attempts=3, retry_base_seconds=0)
    with pytest.raises(LongbridgePermissionError):
        client.query("quote", operation)
    assert attempts == 1


def test_non_transient_error_is_not_retried() -> None:
    client = LongbridgeClient(object(), max_attempts=3, retry_base_seconds=0)
    with pytest.raises(LongbridgeProviderError):
        client.query("static_info", lambda _: (_ for _ in ()).throw(RuntimeError("invalid request")))

