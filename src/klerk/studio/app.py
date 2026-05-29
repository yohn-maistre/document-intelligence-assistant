"""Textual Studio TUI entry — 5 panels: corpus / eval / traces / proposals / KG.

Wired in h24–28. Until then, `klerk-studio` prints a placeholder.
"""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "klerk-studio: implemented in h24–28.\n"
        "Will open a Textual TUI with 5 panels. --serve for browser via textual-web.",
        file=sys.stderr,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
