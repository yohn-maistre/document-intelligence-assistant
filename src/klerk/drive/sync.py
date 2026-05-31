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
import mimetypes
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
# Upload uses the narrower `drive.file` scope: the Service Account can only
# see / touch files it created itself, so an upload typo can't reach the rest
# of the reviewer's Drive. (Trade-off: skip-existing only sees prior klerk
# uploads, which is exactly what we want for idempotent re-runs.)
UPLOAD_SCOPE = "https://www.googleapis.com/auth/drive.file"

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
def _build_service(scope: str):
    """Build a Drive v3 client using the Service Account credentials at `scope`."""
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
        creds_path, scopes=[scope]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _service():
    """Read-only Drive client for sync/list/download."""
    return _build_service(DRIVE_SCOPE)


def _service_for_upload():
    """Drive client scoped to `drive.file` for the upload verb."""
    return _build_service(UPLOAD_SCOPE)


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


# ─── Upload (corpus → Drive) ─────────────────────────────────────────────────
@dataclass
class UploadResult:
    """One file's upload outcome."""

    path: str            # local source path
    name: str            # name in Drive
    file_id: str | None  # None when skipped or dry-run
    status: str          # "uploaded" | "skipped" | "dry-run"


@dataclass
class UploadReport:
    folder_id: str
    dry_run: bool
    results: list[UploadResult] = field(default_factory=list)

    @property
    def uploaded(self) -> list[UploadResult]:
        return [r for r in self.results if r.status == "uploaded"]

    @property
    def skipped(self) -> list[UploadResult]:
        return [r for r in self.results if r.status == "skipped"]


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def list_uploaded_names(folder_id: str, *, service=None) -> dict[str, str]:
    """Map `name → file_id` for files the SA already placed in `folder_id`.

    Used for `--skip-existing`. With the `drive.file` scope the SA only sees
    its own uploads, so this is naturally scoped to prior klerk runs.
    """
    svc = service or _service_for_upload()
    out: dict[str, str] = {}
    page_token: str | None = None
    while True:
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name)",
            pageSize=200,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for f in resp.get("files", []):
            out.setdefault(f["name"], f["id"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def upload_file(
    path: Path,
    folder_id: str,
    *,
    service=None,
    name: str | None = None,
) -> str:
    """Upload one local file into `folder_id`. Returns the new Drive file ID."""
    from googleapiclient.http import MediaFileUpload

    svc = service or _service_for_upload()
    drive_name = name or path.name
    metadata = {"name": drive_name, "parents": [folder_id]}
    media = MediaFileUpload(str(path), mimetype=_guess_mime(path), resumable=True)
    created = svc.files().create(
        body=metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def upload_directory(
    src: str | Path,
    folder_id: str | None = None,
    *,
    glob: str = "*",
    skip_existing: bool = True,
    dry_run: bool = False,
    service=None,
) -> UploadReport:
    """Upload files under `src` matching `glob` into the Drive `folder_id`.

    - `dry_run=True` never calls the Drive API beyond the (read-only) listing
      used for skip-existing; every result is marked `"dry-run"`.
    - `skip_existing=True` skips files whose name already exists in the folder
      (from a prior klerk upload).
    """
    folder_id = folder_id or os.environ.get("DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError(
            "upload: folder_id arg or DRIVE_FOLDER_ID env var required."
        )
    src_path = Path(src)
    if not src_path.exists():
        raise RuntimeError(f"upload: source path not found: {src_path}")

    if src_path.is_file():
        files = [src_path]
    else:
        files = sorted(p for p in src_path.glob(glob) if p.is_file())

    existing: dict[str, str] = {}
    if skip_existing and (files or not dry_run):
        try:
            existing = list_uploaded_names(folder_id, service=service)
        except Exception:  # noqa: BLE001 - listing is best-effort for skip logic
            existing = {}

    report = UploadReport(folder_id=folder_id, dry_run=dry_run)
    for path in files:
        if skip_existing and path.name in existing:
            report.results.append(
                UploadResult(str(path), path.name, existing[path.name], "skipped")
            )
            continue
        if dry_run:
            report.results.append(UploadResult(str(path), path.name, None, "dry-run"))
            continue
        try:
            file_id = upload_file(path, folder_id, service=service)
        except Exception as e:  # noqa: BLE001 - translate the SA-quota 403 to a clear hint
            if "storagequota" in str(e).lower().replace(" ", ""):
                raise RuntimeError(
                    "Drive upload failed: a Service Account has NO storage quota, so it "
                    "cannot create files in a personal Drive folder — even one shared "
                    "with it as Editor (the SA would own the file). Options:\n"
                    f"  1. Upload the files manually (web UI / rclone) — they're in '{src_path}'.\n"
                    "  2. Use a Google Workspace Shared Drive (point DRIVE_FOLDER_ID at it).\n"
                    "  3. Use OAuth user delegation (roadmap).\n"
                    "klerk's /ingest (READ) path is unaffected — the SA can read a "
                    "shared folder without quota."
                ) from e
            raise
        report.results.append(UploadResult(str(path), path.name, file_id, "uploaded"))
    return report
