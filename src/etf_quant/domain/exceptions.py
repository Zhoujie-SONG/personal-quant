from __future__ import annotations


class DataNormalizationError(ValueError):
    """A raw observation cannot be converted into a canonical value."""


class DataValidationError(ValueError):
    """A canonical value violates a provider-neutral domain invariant."""
