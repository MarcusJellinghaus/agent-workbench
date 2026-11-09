# Step 6 – Public LLM functions in `adapters/llm.py`

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 6
only, test first: the public chat-model, error-mapping and invoke functions that `prompt`, `verify` and
#15 use. Make all checks pass and produce exactly one commit.

## WHERE
- New `src/agent_workbench/adapters/llm.py`
- New `tests/adapters/test_llm.py`

## WHAT
```python
def create_chat_model(config: LLMConfig, timeout: int) -> Any:
    """Return a configured BaseChatModel (Any to mypy: langchain_core is skipped)."""

def map_provider_error(exc: Exception, config: LLMConfig, chat_model: Any) -> NoReturn:
    """Raise the mapped error for an exception from a chat-model call (as mcp_coder's _ask_text).

    Raises:
        LLMAuthError / LLMConnectionError: provider auth / connection failures.
        ValueError: a 404 / model-not-found, with the 404 hint as message.
        Exception: *exc* itself when nothing matches.
    """

def invoke(chat_model: Any, config: LLMConfig, text: str) -> str:
    """Send one prompt and return the answer text; errors go through map_provider_error."""
```

## HOW
- Module level imports only `typing` and `agent_workbench.core.config.LLMConfig` – **no**
  `adapters.langchain` import at module level (keeps `--version` light).
- Inside the functions:
  `from .langchain._setup import _create_chat_model, _handle_provider_error`,
  `from .langchain._config_diagnostics import dialed_url`,
  `from .langchain._errors_404 import _format_404_hint, _is_404_error`.
  Names are looked up in their defining module at call time, so tests patch e.g.
  `agent_workbench.adapters.langchain._setup._create_chat_model`.
- `invoke` passes the plain string to `chat_model.invoke(text)` (BaseChatModel turns a str into one
  human message), so this module needs no `langchain_core` import.
- Callers (services, interfaces, #15) import the module and call `llm.<function>`; tests patch
  `agent_workbench.adapters.llm.<function>` when they want to replace a whole function.

## ALGORITHM
```
create_chat_model(config, timeout): return _create_chat_model(config.as_dict(), timeout=timeout)

map_provider_error(exc, config, chat_model):
    _handle_provider_error(exc, config.backend, dialed_url(chat_model))   # raises LLMAuthError / LLMConnectionError
    if _is_404_error(exc): raise ValueError(_format_404_hint(config.as_dict())) from exc
    raise exc

invoke(chat_model, config, text):
    try: msg = chat_model.invoke(text)
    except Exception as exc: map_provider_error(exc, config, chat_model)
    return msg.content if isinstance(msg.content, str) else str(msg.content)
```

## DATA
`str` answer; exceptions as listed. The config passed to the copies is always `config.as_dict()` (a real
`dict` with exactly the five keys – `_format_404_hint` needs a `dict`).

## Tests (write first, `tests/adapters/test_llm.py`)
Use a `MagicMock` chat model (`base_url`-style attributes unset is fine for `dialed_url`). No
`langchain_core` needed:
- `create_chat_model` forwards `config.as_dict()` and `timeout` to `_setup._create_chat_model` (patched);
- `create_chat_model` with `LLMConfig()` raises `ValueError` (real contract check, unset backend);
- `invoke` returns `content` (str) and `str(content)` for non-str content;
- `ConnectionError` from `chat_model.invoke` → `LLMConnectionError`;
- `Exception("404 model not found")` → `ValueError` whose message comes from `_format_404_hint`
  (patch `agent_workbench.adapters.langchain._errors_404._get_model_suggestions` to return `""` – it would
  list models over the network);
- `RuntimeError("boom")` → re-raised unchanged (`is` the original).

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports. One commit:
`Add public chat-model, error-mapping and invoke functions`.
