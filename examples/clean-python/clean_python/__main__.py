"""Command-line entry point for the clean fixture."""

from . import message


def main() -> None:
    """Print the deterministic fixture message."""

    print(message())


if __name__ == "__main__":
    main()
