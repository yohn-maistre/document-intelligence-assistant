"""klerk studio Textual themes.

Default: **klerk-slate** — a calm Tokyo-Night-leaning slate-blue dark palette
(crisp, not neon). Alternates are registered for live switching via the command
palette (Ctrl+P → "Change theme"): **klerk-cyberpunk** (magenta/cyan easter egg)
and **klerk-light** (daytime). Plus a small shared CSS string.
"""

from __future__ import annotations

from textual.theme import Theme

# ── klerk-slate (default) — Tokyo-Night-leaning slate blue ────────────────────
SLATE_BG = "#1a1b26"  # deep slate (not pure black — better glyph contrast)
SLATE_SURFACE = "#1f2335"  # panels / tables
SLATE_PANEL = "#24283b"  # raised panels / headers / status bar
SLATE_FG = "#c0caf5"  # soft blue-white body text
BLUE = "#7aa2f7"  # primary — borders, focus, headings
CYAN = "#7dcfff"  # secondary — links, tool cards, sparklines
LAVENDER = "#bb9af7"  # accent — tasteful pop
SUCCESS = "#9ece6a"
WARNING = "#e0af68"
ERROR = "#f7768e"

KLERK_SLATE = Theme(
    name="klerk-slate",
    primary=BLUE,
    secondary=CYAN,
    accent=LAVENDER,
    background=SLATE_BG,
    surface=SLATE_SURFACE,
    panel=SLATE_PANEL,
    foreground=SLATE_FG,
    success=SUCCESS,
    warning=WARNING,
    error=ERROR,
    dark=True,
    variables={
        "border": BLUE,
        "border-blurred": "#3b4261",  # mid-slate — unfocused panes still show a line
        "footer-key-foreground": CYAN,
        "input-cursor-background": BLUE,
        "input-selection-background": "#7aa2f733",
        "scrollbar": "#2a2e42",
        "scrollbar-hover": BLUE,
        "link-color": CYAN,
    },
)

# ── klerk-cyberpunk (alt / easter egg) — magenta + cyan over near-black ───────
KLERK_CYBER = Theme(
    name="klerk-cyberpunk",
    primary="#ff2bd6",
    secondary="#22d3ee",
    accent="#22d3ee",
    background="#0a0b10",
    surface="#12141c",
    panel="#181b26",
    foreground="#e6e6f0",
    success="#39ff8a",
    warning="#ffc857",
    error="#ff5c7a",
    dark=True,
    variables={
        "border": "#ff2bd6",
        "border-blurred": "#3a2050",
        "footer-key-foreground": "#22d3ee",
        "input-cursor-background": "#ff2bd6",
        "scrollbar": "#2a1840",
        "scrollbar-hover": "#ff2bd6",
        "link-color": "#22d3ee",
    },
)

# ── klerk-light — daytime / projector ─────────────────────────────────────────
KLERK_LIGHT = Theme(
    name="klerk-light",
    primary="#3457d5",
    secondary="#0e7490",
    accent="#7c3aed",
    background="#f6f7fb",
    surface="#ffffff",
    panel="#eef0f6",
    foreground="#1a1b26",
    success="#1a7f4b",
    warning="#b45309",
    error="#be123c",
    dark=False,
    variables={"border": "#3457d5", "link-color": "#0e7490"},
)

# Registered in order; the first is the default. The built-in command palette's
# "Change theme" entry switches between them live.
KLERK_THEMES = [KLERK_SLATE, KLERK_CYBER, KLERK_LIGHT]
KLERK_THEME = KLERK_SLATE  # the default

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
/* Unobtrusive 1-cell scrollbars everywhere. */
* {
    scrollbar-size-vertical: 1;
    scrollbar-size-horizontal: 1;
}
"""
