"""Redaction shim — re-exports from mcp_coder_utils."""

from mcp_coder_utils.redaction import (
    REDACTED_VALUE,
    SENSITIVE_KEY_PATTERNS,
    token_fingerprint,
)

__all__ = ["REDACTED_VALUE", "SENSITIVE_KEY_PATTERNS", "token_fingerprint"]
