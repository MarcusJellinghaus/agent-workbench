"""Placeholder domain logic for the repo skeleton."""


def greet(name: str = "world") -> str:
    """Build a greeting.

    Args:
        name: Who to greet. Blank names fall back to "world".

    Returns:
        The greeting text.
    """
    cleaned = name.strip() or "world"
    return f"Hello, {cleaned}!"
