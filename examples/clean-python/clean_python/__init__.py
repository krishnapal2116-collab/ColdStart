"""Small dependency-free package for the ColdStart clean fixture."""

__all__ = ["message"]


def message() -> str:
    """Return the fixture's deterministic message."""

    return "clean-python"
