"""List the frameworks the server can see, one per line.

Usage:
    uv run python scripts/list_frameworks.py      (or: make frameworks)

Reads KNOWLEDGE_MCP_FRAMEWORKS if set, otherwise the project's frameworks/ folder.
"""

from __future__ import annotations

import sys

from knowledge_mcp.config import load_settings
from knowledge_mcp.tools.frameworks import load_frameworks


def main() -> int:
    folder = load_settings().frameworks_dir
    frameworks = load_frameworks(folder)
    print(f"Frameworks in {folder}: {len(frameworks)}")
    for name, fw in frameworks.items():
        print(f"  {name} | {fw['category']} | {fw['use_when']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
