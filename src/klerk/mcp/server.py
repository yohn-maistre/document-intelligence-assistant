"""MCP server entry — Hermes-pattern gateway exposing klerk tools over stdio.

Wired in h20.5–22. Until then, `klerk-mcp` prints a placeholder.
"""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "klerk-mcp: implemented in h20.5–22.\n"
        "Will expose 14 tools (search_hybrid, propose_section, extract_kg, ...) over stdio.",
        file=sys.stderr,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
