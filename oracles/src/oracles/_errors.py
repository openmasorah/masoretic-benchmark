"""Oracle exception hierarchy."""

from __future__ import annotations


class OracleError(Exception):
    """Base for oracle-side failures."""


class OracleUnavailable(OracleError):
    """4xx, transport timeout, or max-retry exhaustion. Caller emits None per D-13."""


class OracleMalformed(OracleError):
    """Response shape did not match expected schema. Caller emits None per D-13."""
