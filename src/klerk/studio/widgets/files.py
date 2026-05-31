"""Files pane — a Tree over the corpus dir, ``.klerk/`` state, and outputs.

Read-only navigation of klerk's on-disk surfaces. Roots are resolved
best-effort: a missing directory simply renders as an empty (greyed) node so
the widget composes cleanly on a fresh checkout.
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode

# Files under these names/suffixes are noise in a corpus view.
_SKIP = {".DS_Store", "__pycache__", ".pyc"}
_MAX_PER_DIR = 200


def _corpus_dir() -> Path:
    return Path(os.environ.get("KLERK_CORPUS_DIR", "data/synth/fata_organa"))


def _state_dir() -> Path:
    return Path(os.environ.get("KLERK_STATE_DIR", ".klerk"))


def _output_dir() -> Path:
    return Path("data/output")


class FilesTree(Container):
    """Tree rooted at corpus + ``.klerk/`` + ``data/output/``."""

    DEFAULT_CSS = """
    FilesTree {
        height: 1fr;
        border: solid $primary;
        border-title-color: $primary;
        padding: 0 1;
    }
    FilesTree Tree {
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = "files"
        tree: Tree[Path] = Tree("klerk", id="files-tree")
        tree.root.expand()
        tree.show_root = False
        for label, root in (
            ("corpus", _corpus_dir()),
            (".klerk", _state_dir()),
            ("data/output", _output_dir()),
        ):
            node = tree.root.add(f"[b]{label}[/b]", data=root, expand=True)
            self._populate(node, root)
        yield tree
        yield Static("[dim]read-only · corpus / state / artefacts[/dim]")

    def _populate(self, node: TreeNode[Path], path: Path, depth: int = 0) -> None:
        if depth > 4 or not path.exists() or not path.is_dir():
            if not path.exists():
                node.add_leaf("[dim](not present)[/dim]")
            return
        try:
            entries = sorted(
                path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError:
            node.add_leaf("[dim](unreadable)[/dim]")
            return
        shown = 0
        for entry in entries:
            if entry.name in _SKIP or entry.suffix in _SKIP:
                continue
            if shown >= _MAX_PER_DIR:
                node.add_leaf("[dim]…[/dim]")
                break
            shown += 1
            if entry.is_dir():
                child = node.add(f"[cyan]{entry.name}/[/cyan]", data=entry)
                self._populate(child, entry, depth + 1)
            else:
                node.add_leaf(entry.name, data=entry)
