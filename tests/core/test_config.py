from agent_workbench.core.config import LLM_KEYS, LLMConfig


def test_as_dict_default_has_all_keys_unset() -> None:
    result = LLMConfig().as_dict()
    assert type(result) is dict
    assert result == dict.fromkeys(LLM_KEYS)


def test_as_dict_copies_values() -> None:
    config = LLMConfig(
        backend="openai",
        model="gpt-4o",
        api_key="sk-test",
        base_url="https://example.invalid/v1",
        api_version="2024-06-01",
    )
    result = config.as_dict()
    assert list(result) == list(LLM_KEYS)
    assert result == {
        "backend": "openai",
        "model": "gpt-4o",
        "api_key": "sk-test",
        "base_url": "https://example.invalid/v1",
        "api_version": "2024-06-01",
    }
