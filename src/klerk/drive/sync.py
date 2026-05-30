"""Drive incremental sync.

Two-phase sync:
  1. Bootstrap: `files.list` walks the configured folder, builds a fresh
     manifest, and seeds a `changes.list` startPageToken. Used on first
     run (and any time the persisted state-token is missing).
  2. Incremental: `changes.list` from the stored startPageToken catches up
     to "now"; the change set is reconciled against the manifest and only
     added/changed files are re-downloaded.

The manifest primitive is storage-agnostic (key = Drive file ID, value =
md5Checksum or modifiedTime). Native Drive files (Docs / Sheets / Slides)
are exported to Office formats so Docling can parse them.

Auth: Service Account via `GOOGLE_APPLICATION_CREDENTIALS` pointing to a
JSON keyfile. The reviewer shares the Drive folder with the SA's email
address (Viewer is enough).
"""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# Native Drive types → export to formats Docling parses cleanly.
EXPORT_MIME = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}

# Drive folders themselves aren't downloadable; skip them in walks.
FOLDER_MIME = "application/vnd.google-apps.folder"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


# ─── Manifest primitive (step 1 origin; preserved) ───────────────────────────
def manifest_path() -> Path:
    p = Path(os.environ.get("KLERK_DRIVE_MANIFEST", ".klerk/drive-manifest.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def page_token_path() -> Path:
    return manifest_path().with_name("drive-page-token.json")


def download_dir() -> Path:
    p = Path(os.environ.get("KLERK_DRIVE_DOWNLOAD_DIR", "data/drive"))
    p.mkdir(parents=True, exist_ok=True)
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
    p = manifest_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_manifest(state: dict[str, str]) -> None:
    p = manifest_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(p)


def diff_manifest(current: dict[str, str], previous: dict[str, str]) -> ManifestDiff:
    current_keys = set(current)
    previous_keys = set(previous)
    return ManifestDiff(
        added=sorted(current_keys - previous_keys),
        changed=sorted(
            k for k in (current_keys & previous_keys) if current[k] != previous[k]
        ),
        removed=sorted(previous_keys - current_keys),
    )


def load_page_token() -> str | None:
    p = page_token_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return data.get("token")
    except (OSError, json.JSONDecodeError):
        return None


def save_page_token(token: str) -> None:
    p = page_token_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"token": token}, indent=2))
    tmp.replace(p)


# ─── Drive API client ────────────────────────────────────────────────────────
def _service():
    """Build a Drive v3 client using the Service Account credentials."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS unset. Point it at the Service "
            "Account JSON keyfile; share the Drive folder with the SA's email."
        )
    if not Path(creds_path).exists():
        raise RuntimeError(f"GOOGLE_APPLICATION_CREDENTIALS file not found: {creds_path}")

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=[DRIVE_SCOPE]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ─── List + token bootstrap ──────────────────────────────────────────────────
def list_folder(folder_id: str, *, service=None) -> list[dict[str, Any]]:
    """Recursively list non-folder files under `folder_id`. Returns metadata dicts."""
    svc = service or _service()
    out: list[dict[str, Any]] = []
    pending: list[str] = [folder_id]
    visited: set[str] = set()

    fields = (
        "nextPageToken,"
        "files(id,name,mimeType,modifiedTime,md5Checksum,size,parents)"
    )

    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)

        page_token: str | None = None
        while True:
            resp = svc.files().list(
                q=f"'{current}' in parents and trashed=false",
                fields=fields,
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                if f["mimeType"] == FOLDER_MIME:
                    pending.append(f["id"])
                else:
                    out.append(f)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return out


def fetch_start_page_token(*, service=None) -> str:
    """Get a fresh startPageToken to track future changes from."""
    svc = service or _service()
    resp = svc.changes().getStartPageToken(supportsAllDrives=True).execute()
    return resp["startPageToken"]


def fetch_changes(start_token: str, *, service=None) -> tuple[list[dict[str, Any]], str]:
    """Pull all changes since `start_token`. Returns (changes, new_start_token)."""
    svc = service or _service()
    changes: list[dict[str, Any]] = []
    page_token: str | None = start_token
    new_start_token = start_token

    fields = (
        "newStartPageToken,nextPageToken,"
        "changes(fileId,removed,"
        "file(id,name,mimeType,modifiedTime,md5Checksum,parents))"
    )
    while page_token:
        resp = svc.changes().list(
            pageToken=page_token,
            fields=fields,
            includeRemoved=True,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        changes.extend(resp.get("changes", []))
        if "newStartPageToken" in resp:
            new_start_token = resp["newStartPageToken"]
        page_token = resp.get("nextPageToken")
    return changes, new_start_token


# ─── Download ────────────────────────────────────────────────────────────────
def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("_")
    return cleaned or "file"


def _local_path(file_id: str, name: str, mime_type: str, root: Path) -> Path:
    """Stable local path: `{file_id}__{safe_name}{ext}`. file_id prefix guarantees uniqueness."""
    if mime_type in EXPORT_MIME:
        _, ext = EXPORT_MIME[mime_type]
    else:
        # Best-effort suffix from the upstream name; fall back to .bin
        ext = Path(name).suffix or ".bin"
    base = Path(name).stem
    return root / f"{file_id}__{_safe_name(base)}{ext}"


def download_file(meta: dict[str, Any], *, root: Path, service=None) -> Path:
    """Download (or export) one Drive file to `root`. Returns the local path."""
    from googleapiclient.http import MediaIoBaseDownload

    svc = service or _service()
    file_id = meta["id"]
    mime = meta["mimeType"]

    if mime in EXPORT_MIME:
        export_mime, _ = EXPORT_MIME[mime]
        request = svc.files().export_media(fileId=file_id, mimeType=export_mime)
    elif mime == FOLDER_MIME:
        raise ValueError(f"refusing to download a folder: {file_id}")
    else:
        request = svc.files().get_media(fileId=file_id, supportsAllDrives=True)

    out = _local_path(file_id, meta.get("name", file_id), mime, root)
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    out.write_bytes(buf.getvalue())
    return out


def _remove_local(file_id: str, root: Path) -> int:
    """Delete any local file whose name starts with `{file_id}__`. Returns count."""
    if not root.exists():
        return 0
    n = 0
    for p in root.glob(f"{file_id}__*"):
        try:
            p.unlink()
            n += 1
        except OSError:
            continue
    return n


# ─── End-to-end sync ─────────────────────────────────────────────────────────
@dataclass
class SyncReport:
    folder_id: str
    bootstrap: bool             # True on first run (no prior page token)
    diff: ManifestDiff
    downloaded: list[Path]
    removed: list[str]          # file IDs whose local files were deleted
    page_token: str             # the new startPageToken to persist
    download_dir: str


def _current_manifest_from_listing(files: list[dict[str, Any]]) -> dict[str, str]:
    """Build a `file_id → version` map. Prefer md5Checksum; fall back to modifiedTime."""
    return {
        f["id"]: (f.get("md5Checksum") or f.get("modifiedTime") or "")
        for f in files
    }


def sync(
    folder_id: str | None = None,
    *,
    service=None,
    root: Path | None = None,
) -> SyncReport:
    """Bootstrap or incremental sync, depending on persisted state.

    - First run (no page token): full list_folder walk → seed manifest +
      download all → fetch_start_page_token → persist token. The diff
      reports everything as `added`.
    - Subsequent runs: changes.list from persisted token; reconcile changes
      against the manifest; download added/changed; remove deleted; persist
      the new page token.
    """
    folder_id = folder_id or os.environ.get("DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError(
            "sync: folder_id arg or DRIVE_FOLDER_ID env var required."
        )
    root = root or download_dir()

    persisted_token = load_page_token()
    previous = load_manifest()

    if persisted_token is None:
        # ── Bootstrap: full walk ──
        listing = list_folder(folder_id, service=service)
        current = _current_manifest_from_listing(listing)
        diff = diff_manifest(current, previous)  # everything is `added` on the very first run

        downloaded: list[Path] = []
        for fid in diff.added + diff.changed:
            meta = next((f for f in listing if f["id"] == fid), None)
            if meta is None:
                continue
            try:
                downloaded.append(download_file(meta, root=root, service=service))
            except Exception:  # noqa: BLE001 - one bad file shouldn't kill the sync
                continue

        removed: list[str] = []
        for fid in diff.removed:
            if _remove_local(fid, root):
                removed.append(fid)

        save_manifest(current)
        new_token = fetch_start_page_token(service=service)
        save_page_token(new_token)
        return SyncReport(
            folder_id=folder_id,
            bootstrap=True,
            diff=diff,
            downloaded=downloaded,
            removed=removed,
            page_token=new_token,
            download_dir=str(root),
        )

    # ── Incremental: changes.list ──
    changes, new_token = fetch_changes(persisted_token, service=service)
    current = dict(previous)  # we'll mutate to reflect the changes
    downloaded = []
    removed = []
    folder_set = {folder_id}  # ignore changes outside the watched folder

    for change in changes:
        file_id = change.get("fileId")
        if not file_id:
            continue
        file_meta = change.get("file") or {}
        # Drop changes for files not under our watched folder (best effort:
        # checks parents; if no parents in the change payload, keep it).
        parents = file_meta.get("parents") or []
        if parents and not any(p in folder_set for p in parents):
            continue

        if change.get("removed") or file_meta.get("trashed"):
            if file_id in current:
                current.pop(file_id, None)
                if _remove_local(file_id, root):
                    removed.append(file_id)
            continue

        if file_meta.get("mimeType") == FOLDER_MIME:
            continue

        version = file_meta.get("md5Checksum") or file_meta.get("modifiedTime") or ""
        prev_version = previous.get(file_id)
        if prev_version == version and prev_version:
            # No real content change; skip the download.
            continue
        current[file_id] = version
        try:
            downloaded.append(download_file(file_meta, root=root, service=service))
        except Exception:  # noqa: BLE001
            continue

    diff = diff_manifest(current, previous)
    save_manifest(current)
    save_page_token(new_token)
    return SyncReport(
        folder_id=folder_id,
        bootstrap=False,
        diff=diff,
        downloaded=downloaded,
        removed=removed,
        page_token=new_token,
        download_dir=str(root),
    )
