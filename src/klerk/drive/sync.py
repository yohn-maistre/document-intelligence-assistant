"""Drive incremental sync — step 1 scaffolding: manifest-diff primitive.

The full Drive integration (Service Account auth, `files.list` walk,
`changes.list` with stored `pageToken`, file download, parse → upsert
pipeline) lands in step 3. This module exposes the generic
manifest-diff primitive that both the bootstrap walk and the incremental
`changes.list` path will use.

Manifest contract:
  - Key   = a stable identifier (Drive file ID; or a local path during the
            bootstrap walk). Strings.
  - Value = a change-detection token (Drive's `modifiedTime` or
            `md5Checksum`; or a sha256 hex). Strings.
  - State persisted as JSON at `.klerk/drive-manifest.json` (overridable
            via `KLERK_DRIVE_MANIFEST`).

The primitive is intentionally storage- and source-agnostic so the same
diff loop can compare local snapshots during testing and Drive snapshots
in production without branching.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def manifest_path() -> Path:
    p = Path(os.environ.get("KLERK_DRIVE_MANIFEST", ".klerk/drive-manifest.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class ManifestDiff:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.removed)


def load_manifest() -> dict[str, str]:
    """Read the persisted manifest. Returns {} if the file is absent or unreadable."""
    p = manifest_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_manifest(state: dict[str, str]) -> None:
    """Write the manifest atomically (write → replace) to avoid torn reads."""
    p = manifest_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(p)


def diff_manifest(current: dict[str, str], previous: dict[str, str]) -> ManifestDiff:
    """Classify keys as added / changed / removed.

    A key is `added` if it's in `current` but not `previous`;
    `removed` if in `previous` but not `current`;
    `changed` if in both but with different values.
    """
    current_keys = set(current)
    previous_keys = set(previous)
    return ManifestDiff(
        added=sorted(current_keys - previous_keys),
        changed=sorted(
            k for k in (current_keys & previous_keys) if current[k] != previous[k]
        ),
        removed=sorted(previous_keys - current_keys),
    )
