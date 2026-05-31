"""XDG path resolution + project-local override precedence.

Uses monkeypatched env + tmp dirs so nothing touches the real home / cwd.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from klerk import paths


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Neutralize all path-affecting env + cwd for each test."""
    for var in (
        "KLERK_STATE_DIR",
        "KLERK_LANCEDB_DIR",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(var, raising=False)
    # Run from an empty tmp cwd so no stray ./.klerk/ leaks in.
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    # Pin HOME so the ~/.local/share fallback is deterministic.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return tmp_path


def test_xdg_data_home_default(monkeypatch, tmp_path):
    """No env, no ./.klerk → ~/.local/share/klerk."""
    home = tmp_path / "home"
    assert paths.data_root() == home / ".local" / "share" / "klerk"


def test_xdg_data_home_override(monkeypatch, tmp_path):
    xdg = tmp_path / "xdgdata"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    assert paths.data_root() == xdg / "klerk"
    assert paths.sessions_dir() == xdg / "klerk" / "sessions"
    assert paths.memory_dir() == xdg / "klerk" / "memory"
    assert paths.lancedb_dir() == xdg / "klerk" / "lancedb"


def test_xdg_config_default_and_override(monkeypatch, tmp_path):
    home = tmp_path / "home"
    assert paths.config_path() == home / ".config" / "klerk" / "config.yaml"
    xdg = tmp_path / "xdgcfg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert paths.config_path() == xdg / "klerk" / "config.yaml"
    # config_dir is created, config file is not
    assert paths.config_dir().is_dir()
    assert not paths.config_path().exists()


def test_state_dir_env_override_wins(monkeypatch, tmp_path):
    """KLERK_STATE_DIR forces the project-local root over XDG."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    forced = tmp_path / "forced-state"
    monkeypatch.setenv("KLERK_STATE_DIR", str(forced))
    assert paths.data_root() == forced
    assert paths.sessions_dir() == forced / "sessions"
    assert paths.memory_dir() == forced / "memory"


def test_project_local_klerk_dir_detected(monkeypatch, tmp_path):
    """An existing ./.klerk/ in cwd takes precedence over XDG fallback."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    work = tmp_path / "work"
    (work / ".klerk").mkdir()
    assert paths.data_root() == work / ".klerk"


def test_explicit_state_dir_beats_existing_project_local(monkeypatch, tmp_path):
    """KLERK_STATE_DIR outranks a present ./.klerk/."""
    work = tmp_path / "work"
    (work / ".klerk").mkdir()
    forced = tmp_path / "forced"
    monkeypatch.setenv("KLERK_STATE_DIR", str(forced))
    assert paths.data_root() == forced


def test_lancedb_dir_pin_honored(monkeypatch, tmp_path):
    """KLERK_LANCEDB_DIR pins the lancedb dir independent of data_root."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    pinned = tmp_path / "mylance"
    monkeypatch.setenv("KLERK_LANCEDB_DIR", str(pinned))
    assert paths.lancedb_dir() == pinned
    assert pinned.is_dir()


def test_dir_helpers_create_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    assert paths.sessions_dir().is_dir()
    assert paths.memory_dir().is_dir()
    assert paths.lancedb_dir().is_dir()
    assert paths.state_dir().is_dir()
