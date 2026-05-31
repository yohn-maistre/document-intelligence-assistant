"""Studio floor + bonus widgets.

Floor (always ship): FilesTree, LiveChat, ActivityTable, StatusBar, TracesPanel.
Bonus (per D6 cut order): EvalPanel, KgSnapshot, SparkGraph.
"""

from __future__ import annotations

from klerk.studio.widgets.activity import ActivityTable
from klerk.studio.widgets.files import FilesTree
from klerk.studio.widgets.live_chat import LiveChat
from klerk.studio.widgets.status_bar import StatusBar
from klerk.studio.widgets.traces import TracesPanel

__all__ = [
    "ActivityTable",
    "FilesTree",
    "LiveChat",
    "StatusBar",
    "TracesPanel",
]

# Bonus widgets are imported lazily by app.py so the floor never depends on them.
