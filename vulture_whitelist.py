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

# adapters/langchain/_config_diagnostics.py: Finding TypedDict field, read by consumers via dict access
_.ok
# adapters/langchain/_config_diagnostics.py: ResolvedTarget field, read by the copied tests
_.verified
# adapters/langchain/_errors_404.py: 404 helpers, used by adapters.llm (#14 step 6) and the copied tests
_._is_404_error
_._format_404_hint
# adapters/langchain/_exceptions.py: kept from mcp_coder; raised by the agent layer (#15)
_.LLMMCPLaunchError
# adapters/langchain/_exceptions.py: connection diagnostics, used by services.verify and the copied tests
_.format_diagnostics
# adapters/langchain/_messages.py: message helpers, used by the agent layer (#15) and the copied tests
_.assemble_messages
_.serialize_messages
# adapters/langchain/_preflight.py: Ollama agent-mode pre-flight, used by the agent layer (#15)
_._ollama_preflight
# adapters/langchain/_provider_checks.py: provider checks, used by services.verify and the copied tests
_.check_provider
# adapters/langchain/_setup.py: system-message builder and error mapping, used by adapters.llm
_._build_system_messages
_._handle_provider_error
# adapters/langchain/_usage.py: usage helpers, used by the agent layer (#15) and the copied tests
_._extract_usage
_._sum_usage

# tests/adapters/langchain/conftest.py: autouse session fixture for mocking langchain modules
_._mock_langchain_modules
# tests/adapters/langchain/conftest.py: fake langchain_core.messages attribute, read by the code under test
_.ToolMessage
# tests/adapters/langchain/test_langchain_{anthropic,gemini,http,ollama,openai}.py: MagicMock
# return values, read when the code under test calls the mock
_.return_value
# tests/adapters/langchain/test_langchain_{contract,provider_checks,resolve_target}.py:
# autouse fixtures clearing credential, endpoint and redirect env vars
_._clear_credentials
_._clear_env
_._clear_redirects
