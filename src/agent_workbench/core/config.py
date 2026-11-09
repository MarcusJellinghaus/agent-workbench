"""LLM configuration type: the keys of the ``[llm]`` config section."""

from dataclasses import asdict, dataclass

LLM_KEYS: tuple[str, ...] = ("backend", "model", "api_key", "base_url", "api_version")


@dataclass(frozen=True)
class LLMConfig:
    """The [llm] section: keys of mcp_coder's [llm.langchain]."""

    backend: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a real dict with exactly the five keys (the copied functions need a dict).

        Returns:
            Mapping of every key in ``LLM_KEYS`` to its value.
        """
        return asdict(self)
