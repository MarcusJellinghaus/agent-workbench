"""Vulture whitelist - false positives and intentionally kept code.

This file tells Vulture to ignore items that appear unused but are
intentionally kept (framework hooks, pytest fixtures, entry points).

Format: _.attribute_name (Vulture's attribute-style whitelist syntax)

Review this list periodically - items may become used or truly dead over time.
"""

# adapters/llm_types.py: UsageInfo field read by consumers via dict access
_.cache_creation_input_tokens
# adapters/llm_types.py: UsageInfo fields
_.input_tokens
_.output_tokens
_.cache_read_input_tokens
# adapters/llm_types.py: LLMResponseDict field
_.timestamp
# adapters/llm_types.py: ResponseAssembler API, used by the copied model layer's consumers
_.add
_.has_error
# tests/adapters/test_ssl_setup.py: autouse fixture
_._reset_injected
