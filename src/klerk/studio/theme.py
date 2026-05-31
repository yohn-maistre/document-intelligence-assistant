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

# klerk-slate — a lower-saturation cyan-on-slate skin. Easier on the eyes in the
# browser (textual-serve) and on terminals where hot magenta-on-black is harsh.
KLERK_SLATE = Theme(
    name="klerk-slate",
    primary=CYAN,
    secondary="#7aa2f7",
    accent=CYAN,
    background="#0d1117",
    surface="#11161f",
    panel="#161c28",
    foreground="#c9d1d9",
    success=SUCCESS,
    warning=WARNING,
    error=ERROR,
    dark=True,
    variables={
        "border": CYAN,
        "border-blurred": "#1f2a3a",
        "footer-key-foreground": CYAN,
        "link-color": "#7aa2f7",
    },
)

# klerk-light — daytime / projector palette (dark=False).
KLERK_LIGHT = Theme(
    name="klerk-light",
    primary="#b3008f",
    secondary="#0e7490",
    accent="#0e7490",
    background="#f6f7fb",
    surface="#ffffff",
    panel="#eef0f6",
    foreground="#1a1b26",
    success="#1a7f4b",
    warning="#b45309",
    error="#be123c",
    dark=False,
    variables={"border": "#b3008f", "link-color": "#0e7490"},
)

# Registered in order; the first is the default. The built-in command palette's
# "Change theme" entry switches between them live (Textual ≥8).
KLERK_THEMES = [KLERK_THEME, KLERK_SLATE, KLERK_LIGHT]


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
