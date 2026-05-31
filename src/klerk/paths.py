"""XDG-aware path resolution for klerk's on-disk state.

Resolution strategy (Aider-style project-local override):

  1. **Project-local override** — if a `./.klerk/` directory exists in the
     current working directory (or `KLERK_STATE_DIR` is set), all state lives
     under it. This keeps a checked-out repo self-contained for dev / demo and
     matches the legacy `.klerk/` convention used across the codebase.
  2. **XDG data** — otherwise data dirs resolve under
     `${XDG_DATA_HOME:-~/.local/share}/klerk/{sessions,memory,lancedb}`.
  3. **XDG config** — `${XDG_CONFIG_HOME:-~/.config}/klerk/config.yaml`.

Env overrides (highest precedence, evaluated per-call so tests can monkeypatch):

  - `KLERK_STATE_DIR`  — forces the project-local data root (legacy var).
  - `KLERK_LANCEDB_DIR` — pins the LanceDB directory specifically (legacy var,
    honored by `rag/store.py`).
  - `XDG_DATA_HOME` / `XDG_CONFIG_HOME` — standard XDG base-dir overrides.

All directory helpers create the directory (and parents) on access so callers
can write immediately. `config_path()` does NOT create the file.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "klerk"

# Legacy / project-local default root. Honored when `KLERK_STATE_DIR` is set or
# when a `./.klerk/` directory already exists next to the working directory.
_PROJECT_LOCAL_DIRNAME = ".klerk"


def _project_local_root() -> Path | None:
    """Return the project-local `.klerk/` root if one is in effect, else None.

    A project-local root is active when either:
      - `KLERK_STATE_DIR` is set (explicit opt-in / legacy behavior), or
      - a `./.klerk/` directory already exists in the current working dir.
    """
    explicit = os.environ.get("KLERK_STATE_DIR")
    if explicit:
        return Path(explicit)
    candidate = Path.cwd() / _PROJECT_LOCAL_DIRNAME
    if candidate.is_dir():
        return candidate
    return None


def _xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "share"


def _xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".config"


def data_root() -> Path:
    """Resolve the klerk data root (project-local override or XDG data home).

    Does not create the directory; the typed sub-dir helpers below do.
    """
    project = _project_local_root()
    if project is not None:
        return project
    return _xdg_data_home() / APP_NAME


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    """The root directory for all mutable klerk state. Created on access."""
    return _ensure(data_root())


def sessions_dir() -> Path:
    """Directory for chat-session JSONL transcripts. Created on access."""
    return _ensure(data_root() / "sessions")


def memory_dir() -> Path:
    """Directory for long-term memory (SOUL.md / MEMORY.md). Created on access."""
    return _ensure(data_root() / "memory")


def lancedb_dir() -> Path:
    """Directory for the LanceDB store. Created on access.

    Honors the legacy `KLERK_LANCEDB_DIR` pin first so existing deployments
    and `rag/store.py` keep their configured location.
    """
    pinned = os.environ.get("KLERK_LANCEDB_DIR", "").strip()
    if pinned:
        return _ensure(Path(pinned))
    return _ensure(data_root() / "lancedb")


def config_dir() -> Path:
    """The XDG config directory for klerk. Created on access."""
    return _ensure(_xdg_config_home() / APP_NAME)


def config_path() -> Path:
    """Path to `config.yaml` under the XDG config dir. The file is NOT created."""
    return config_dir() / "config.yaml"
