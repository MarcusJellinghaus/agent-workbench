# Step 3 – OpenAI streamed usage in `create_chat_model`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 3: make the OpenAI chat
model built by `adapters.llm.create_chat_model` carry langchain_openai's own `stream_usage`
default, which the copied backend loses by passing its own HTTP clients. Probe first,
tests next, then code; all checks pass; one commit.

## Precondition
`langchain_openai` and `langchain_core` must be resolvable
(`mcp__mcp-tools-py__search_library_files(scope=..., glob="__init__.py")`). Otherwise write
one line to `pr_info/.blocked.txt` and stop.

## WHERE
- Modify `src/agent_workbench/adapters/llm.py`
- Create `tests/adapters/test_llm_stream_usage.py`
- No change to any copied file (`adapters/langchain/*`).

## WHAT
```python
def create_chat_model(config: LLMConfig, timeout: int) -> Any:   # unchanged signature
def _mirror_openai_stream_usage(chat_model: Any) -> None:
    """Set *chat_model*.stream_usage to what langchain_openai picks without custom clients."""
```

## HOW
- `create_chat_model` calls `_mirror_openai_stream_usage(model)` when
  `config.backend == "openai"` (covers Azure – same backend), then returns the model.
  The existing test patching `_create_chat_model` with a sentinel uses an Ollama config and
  stays green.
- No list of langchain_openai's conditions (base-URL / proxy env vars, LangSmith gateway,
  Azure): the reference instance decides.
- Probe first (`.scratch/test_probe.py`, run with
  `run_pytest_check(extra_args=["-p", "no:cacheprovider", ".scratch/test_probe.py"])`):
  1. which init values to reuse – build a `ChatOpenAI(model=..., api_key="x", base_url=..., timeout=5, http_client=..., http_async_client=...)`
     and inspect `model_fields_set`; it must give the user-passed fields (exclude
     `http_client`, `http_async_client`, `stream_usage` and any client field the validator
     set);
  2. building the reference makes no network call;
  3. `chat_model.stream_usage = True` on the built model makes a streamed call request usage
     (e.g. `chat_model._get_request_payload(...)` / `_should_stream_usage()` reflects it).
  If (3) fails, pass it per call instead: add `stream_usage_kwargs(chat_model) -> dict[str, Any]`
  returning `{"stream_usage": value}` or `{}` and note in step 5 that the model node passes
  `**llm.stream_usage_kwargs(chat_model)` to `ainvoke`.
- Delete `.scratch/` before committing.

## ALGORITHM
```
init = {name: getattr(model, name) for name in model.model_fields_set
        if name not in _CLIENT_FIELDS | {"stream_usage"}}
reference = type(model)(**init)          # same class, same settings, no custom clients
model.stream_usage = reference.stream_usage
```
(`_CLIENT_FIELDS` = the client field names found by the probe.)

## DATA
No new return values; the OpenAI model's `stream_usage` attribute is set.

## Tests (`tests/adapters/test_llm_stream_usage.py`)
Real `langchain_openai`, imported directly (no `importorskip`; the precondition
guarantees it, and the file lies outside `tests/adapters/langchain/`, whose session-scoped
`_mock_langchain_modules` would substitute mocks for missing packages). Autouse fixture clears `OPENAI_BASE_URL`,
`OPENAI_API_BASE`, `OPENAI_PROXY`, `AZURE_OPENAI_ENDPOINT` and the LangSmith vars found in
the probe; sets a fake `OPENAI_API_KEY` / `AZURE_OPENAI_API_KEY`.
- OpenAI, no base URL → built model has `stream_usage` True (set case).
- OpenAI with a custom `base_url` → equals langchain_openai's value (not set case).
- Azure (`api_version` + `base_url`) → equals langchain_openai's own Azure default.
- Non-OpenAI backend (patched `_create_chat_model`) → `_mirror_openai_stream_usage` not called.
Expected literals come from the probe; each test also asserts equality with a reference
built without clients.

## Checks / commit
pylint, pytest, mypy, ruff, vulture. Commit:
`fix(adapters): keep langchain_openai's stream_usage default`.
