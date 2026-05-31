"""Cyberpunk-dark Textual theme for klerk studio.

A magenta + cyan palette (Posting magenta / Dolphie cyan lineage) over a
near-black canvas. Exposed as a Textual ``Theme`` object plus a small CSS
string for widgets that style outside the variable system.
"""

from __future__ import annotations

from textual.theme import Theme

# Core palette ----------------------------------------------------------------
MAGENTA = "#ff2bd6"  # primary accent — prompts, focus, headings
CYAN = "#22d3ee"  # secondary accent — links, tool cards, sparklines
CANVAS = "#0a0b10"  # app background (near-black)
SURFACE = "#12141c"  # panels / tables
PANEL = "#181b26"  # raised panels
FOREGROUND = "#e6e6f0"  # body text
SUCCESS = "#39ff8a"
WARNING = "#ffc857"
ERROR = "#ff5c7a"


KLERK_THEME = Theme(
    name="klerk-cyberpunk",
    primary=MAGENTA,
    secondary=CYAN,
    accent=CYAN,
    background=CANVAS,
    surface=SURFACE,
    panel=PANEL,
    foreground=FOREGROUND,
    success=SUCCESS,
    warning=WARNING,
    error=ERROR,
    dark=True,
    variables={
        "block-cursor-foreground": CANVAS,
        "block-cursor-background": MAGENTA,
        "border": MAGENTA,
        "border-blurred": "#3a2050",
        "footer-key-foreground": CYAN,
        "input-cursor-background": MAGENTA,
        "input-selection-background": "#ff2bd644",
        "scrollbar": "#2a1840",
        "scrollbar-hover": MAGENTA,
        "link-color": CYAN,
    },
)

# Shared app CSS (kept tiny — most styling rides the theme variables) ----------
STUDIO_CSS = """
Screen {
    background: $background;
    color: $foreground;
}
DataTable {
    background: $surface;
}
DataTable > .datatable--header {
    background: $panel;
    color: $secondary;
    text-style: bold;
}
"""
