from __future__ import annotations


class AkShareProviderError(RuntimeError):
    """Base error for the supplemental AkShare adapter."""


class AkShareSchemaError(AkShareProviderError):
    """An upstream DataFrame schema no longer satisfies the explicit contract."""


class AkShareDataError(AkShareProviderError):
    """An upstream value cannot be mapped without guessing or silent coercion."""
