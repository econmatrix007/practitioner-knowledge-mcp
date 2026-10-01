"""Command-line entry point. Transports arrive in Phase 3 (stdio) and Phase 4 (HTTP)."""

import sys

from knowledge_mcp import __version__


def main() -> int:
    print(f"knowledge-mcp {__version__}: server not implemented yet (scaffold).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
