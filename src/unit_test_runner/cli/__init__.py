def main(argv=None):
    """Load the CLI entry point lazily to keep artifact models dependency-safe."""
    from .main import main as entry_point

    return entry_point(argv)


__all__ = ["main"]

__all__ = ["main"]
