from __future__ import annotations

import logging

import pytest

from etf_quant.config.settings import Settings
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.utils.logging import get_logger


def test_credentials_do_not_appear_in_client_repr_or_logs(monkeypatch, caplog) -> None:
    secret = "secret-value-that-must-not-leak"
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", secret)
    client = LongbridgeClient(object(), max_attempts=1)
    assert secret not in repr(client)

    logger = get_logger("tests.credential-redaction")
    with caplog.at_level(logging.WARNING):
        logger.warning("upstream error carried %s", secret)
    assert secret not in caplog.text
    assert "[REDACTED]" in caplog.text


@pytest.mark.parametrize("credential_key", ["app_secret", "custom_access_token", "provider_secret_value"])
def test_settings_reject_credentials_in_yaml(tmp_path, credential_key: str) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(f"longbridge:\n  {credential_key}: forbidden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="credentials"):
        Settings.from_yaml(path)


def test_example_settings_load_without_credentials() -> None:
    settings = Settings.from_yaml(__import__("pathlib").Path("configs/settings.example.yaml"))
    assert settings.provider == "longbridge"
    assert settings.longbridge.max_attempts == 3
    assert settings.daily_bar_availability.eod_delay_minutes == 15


def test_availability_delay_loads_from_yaml(tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "daily_bar_availability:\n  eod_delay_minutes: 25\n",
        encoding="utf-8",
    )
    assert Settings.from_yaml(path).daily_bar_availability.eod_delay_minutes == 25
