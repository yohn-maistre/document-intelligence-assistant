"""Drive incremental sync tests.

The Drive API is mocked end to end via a fake `service` object passed
through `sync(..., service=fake)`. This exercises the real diff loop,
manifest IO, page-token persistence, and local-path generation without
touching the network. Each test isolates state via tmp_path + monkeypatch
of KLERK_DRIVE_MANIFEST / KLERK_DRIVE_DOWNLOAD_DIR.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from klerk.drive import sync as ds


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("KLERK_DRIVE_MANIFEST", str(tmp_path / "drive-manifest.json"))
    monkeypatch.setenv("KLERK_DRIVE_DOWNLOAD_DIR", str(tmp_path / "drive"))
    monkeypatch.setenv("DRIVE_FOLDER_ID", "test_folder_id")
    yield


# ─── Manifest primitive ──────────────────────────────────────────────────────
def test_diff_classifies_added_changed_removed():
    diff = ds.diff_manifest(
        current={"a": "v1", "b": "v2_new", "c": "v3"},
        previous={"a": "v1", "b": "v2_old", "d": "v4"},
    )
    assert diff.added == ["c"]
    assert diff.changed == ["b"]
    assert diff.removed == ["d"]
    assert not diff.empty


def test_diff_empty_when_unchanged():
    diff = ds.diff_manifest({"a": "v1"}, {"a": "v1"})
    assert diff.empty


def test_manifest_roundtrip():
    ds.save_manifest({"file_x": "etag_x"})
    assert ds.load_manifest() == {"file_x": "etag_x"}


def test_load_manifest_returns_empty_on_corrupt_file(tmp_path):
    ds.manifest_path().write_text("not json {{{")
    assert ds.load_manifest() == {}


def test_page_token_roundtrip():
    assert ds.load_page_token() is None
    ds.save_page_token("tok_123")
    assert ds.load_page_token() == "tok_123"


# ─── Mock helpers ────────────────────────────────────────────────────────────
def _make_service(*, list_pages=None, changes_pages=None, start_token="tok_new"):
    """Build a MagicMock Drive service that replays scripted responses.

    list_pages: list of dicts, each one a `files().list().execute()` page.
                If None, returns one page of [].
    changes_pages: same shape for `changes().list().execute()`.
    """
    svc = MagicMock()

    # files().list()
    list_pages = list_pages or [{"files": []}]
    list_iter = iter(list_pages)
    svc.files.return_value.list.return_value.execute.side_effect = lambda: next(list_iter)

    # changes().getStartPageToken().execute() → {"startPageToken": ...}
    svc.changes.return_value.getStartPageToken.return_value.execute.return_value = {
        "startPageToken": start_token,
    }

    # changes().list().execute()
    changes_pages = changes_pages or [{"changes": [], "newStartPageToken": start_token}]
    changes_iter = iter(changes_pages)
    svc.changes.return_value.list.return_value.execute.side_effect = lambda: next(changes_iter)

    # files().get_media() / export_media() → request objects that
    # MediaIoBaseDownload will iterate. We patch the downloader below at
    # module level so these don't actually need to be real.
    svc.files.return_value.get_media.return_value = MagicMock()
    svc.files.return_value.export_media.return_value = MagicMock()

    return svc


@pytest.fixture
def fake_downloader(monkeypatch):
    """Patch MediaIoBaseDownload so download_file writes predictable bytes."""
    class _FakeDownloader:
        def __init__(self, buf: io.BytesIO, _request):
            self._buf = buf
            self._written = False

        def next_chunk(self):
            if not self._written:
                self._buf.write(b"fake-content")
                self._written = True
            return None, True

    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", _FakeDownloader)
    yield


# ─── Bootstrap sync ──────────────────────────────────────────────────────────
def test_bootstrap_walks_lists_downloads_and_seeds_token(fake_downloader, tmp_path):
    listing = [
        {"id": "f1", "name": "memo.pdf", "mimeType": "application/pdf",
         "modifiedTime": "2026-05-29T10:00:00Z", "md5Checksum": "md5_1"},
        {"id": "f2", "name": "leave_policy", "mimeType": "application/vnd.google-apps.document",
         "modifiedTime": "2026-05-29T11:00:00Z"},
    ]
    svc = _make_service(
        list_pages=[{"files": listing}],
        start_token="tok_fresh",
    )

    report = ds.sync(service=svc)

    assert report.bootstrap is True
    assert sorted(report.diff.added) == ["f1", "f2"]
    assert report.diff.changed == []
    assert report.diff.removed == []
    assert len(report.downloaded) == 2
    assert report.page_token == "tok_fresh"

    # Manifest + token persisted
    assert ds.load_manifest() == {"f1": "md5_1", "f2": "2026-05-29T11:00:00Z"}
    assert ds.load_page_token() == "tok_fresh"

    # Local files exist on the predictable path
    assert any(p.name.startswith("f1__") for p in Path(report.download_dir).iterdir())
    assert any(p.name.startswith("f2__") and p.suffix == ".docx"
               for p in Path(report.download_dir).iterdir())


def test_bootstrap_skips_folders_in_listing(fake_downloader):
    listing = [
        {"id": "subfolder", "name": "sub", "mimeType": ds.FOLDER_MIME,
         "modifiedTime": "2026-05-29T10:00:00Z"},
        {"id": "f1", "name": "x.txt", "mimeType": "text/plain",
         "md5Checksum": "md5_1"},
    ]

    # First list call returns the items in the root folder; the recursive
    # walk will then call list() on `subfolder` — we script an empty page
    # for that follow-up.
    svc = _make_service(
        list_pages=[{"files": listing}, {"files": []}],
    )
    report = ds.sync(service=svc)
    assert sorted(report.diff.added) == ["f1"]


def test_bootstrap_handles_paginated_listing(fake_downloader):
    svc = _make_service(
        list_pages=[
            {"files": [{"id": f"f{i}", "name": f"doc{i}.pdf",
                        "mimeType": "application/pdf",
                        "md5Checksum": f"md5_{i}"} for i in range(3)],
             "nextPageToken": "page_2"},
            {"files": [{"id": "f4", "name": "doc4.pdf",
                        "mimeType": "application/pdf",
                        "md5Checksum": "md5_4"}]},
        ],
    )
    report = ds.sync(service=svc)
    assert len(report.diff.added) == 4


# ─── Incremental sync ────────────────────────────────────────────────────────
def test_incremental_detects_added_and_changed(fake_downloader):
    # Seed prior state
    ds.save_manifest({"f1": "md5_1"})
    ds.save_page_token("tok_old")

    svc = _make_service(
        changes_pages=[{
            "changes": [
                {  # changed
                    "fileId": "f1",
                    "file": {"id": "f1", "name": "memo.pdf",
                             "mimeType": "application/pdf",
                             "md5Checksum": "md5_1_NEW",
                             "parents": ["test_folder_id"]},
                },
                {  # added
                    "fileId": "f2",
                    "file": {"id": "f2", "name": "minutes.pdf",
                             "mimeType": "application/pdf",
                             "md5Checksum": "md5_2",
                             "parents": ["test_folder_id"]},
                },
            ],
            "newStartPageToken": "tok_after",
        }],
    )
    report = ds.sync(service=svc)
    assert report.bootstrap is False
    assert report.diff.changed == ["f1"]
    assert report.diff.added == ["f2"]
    assert report.page_token == "tok_after"
    assert ds.load_manifest() == {"f1": "md5_1_NEW", "f2": "md5_2"}


def test_incremental_handles_removed(fake_downloader):
    ds.save_manifest({"f1": "md5_1"})
    ds.save_page_token("tok_old")

    # Pre-create a local file so we can verify cleanup
    local = ds.download_dir() / "f1__memo.pdf"
    local.write_bytes(b"stale")

    svc = _make_service(
        changes_pages=[{
            "changes": [{"fileId": "f1", "removed": True}],
            "newStartPageToken": "tok_after",
        }],
    )
    report = ds.sync(service=svc)
    assert report.diff.removed == ["f1"]
    assert "f1" in report.removed
    assert ds.load_manifest() == {}
    assert not local.exists()


def test_incremental_skips_unchanged_versions(fake_downloader):
    ds.save_manifest({"f1": "md5_1"})
    ds.save_page_token("tok_old")

    svc = _make_service(
        changes_pages=[{
            "changes": [{
                "fileId": "f1",
                "file": {"id": "f1", "name": "memo.pdf",
                         "mimeType": "application/pdf",
                         "md5Checksum": "md5_1",  # same as previous
                         "parents": ["test_folder_id"]},
            }],
            "newStartPageToken": "tok_after",
        }],
    )
    report = ds.sync(service=svc)
    assert report.diff.empty
    assert len(report.downloaded) == 0


def test_incremental_ignores_changes_outside_folder(fake_downloader):
    ds.save_manifest({})
    ds.save_page_token("tok_old")

    svc = _make_service(
        changes_pages=[{
            "changes": [{
                "fileId": "f_outside",
                "file": {"id": "f_outside", "name": "other.pdf",
                         "mimeType": "application/pdf",
                         "md5Checksum": "md5_x",
                         "parents": ["some_other_folder"]},
            }],
            "newStartPageToken": "tok_after",
        }],
    )
    report = ds.sync(service=svc)
    assert report.diff.empty


# ─── Local path naming ───────────────────────────────────────────────────────
def test_local_path_uses_file_id_prefix(tmp_path):
    p = ds._local_path(
        "abc123",
        "Q1 Budget Memo.pdf",
        "application/pdf",
        tmp_path,
    )
    assert p.name.startswith("abc123__")
    assert p.suffix == ".pdf"


def test_local_path_uses_export_extension_for_native_docs(tmp_path):
    p = ds._local_path(
        "doc_xyz",
        "Leave Policy",
        "application/vnd.google-apps.document",
        tmp_path,
    )
    assert p.suffix == ".docx"


def test_local_path_strips_unsafe_chars(tmp_path):
    p = ds._local_path(
        "fid",
        "hr / policy v2 (final).pdf",
        "application/pdf",
        tmp_path,
    )
    # Only safe chars survive (alphanum, dot, dash, underscore)
    assert "/" not in p.name
    assert "(" not in p.name


# ─── Missing config ──────────────────────────────────────────────────────────
def test_sync_raises_when_folder_id_missing(monkeypatch):
    monkeypatch.delenv("DRIVE_FOLDER_ID", raising=False)
    with pytest.raises(RuntimeError, match="folder_id"):
        ds.sync()


def test_service_factory_raises_without_creds(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_APPLICATION_CREDENTIALS"):
        ds._service()


def test_service_factory_raises_when_creds_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "does-not-exist.json"))
    with pytest.raises(RuntimeError, match="not found"):
        ds._service()


# ─── Upload ──────────────────────────────────────────────────────────────────
def _make_upload_service(*, existing=None):
    """MagicMock Drive service for upload: scripts files().list + files().create."""
    svc = MagicMock()
    existing = existing or []
    svc.files.return_value.list.return_value.execute.return_value = {"files": existing}

    counter = {"n": 0}

    def _create(**_kwargs):
        counter["n"] += 1
        m = MagicMock()
        m.execute.return_value = {"id": f"new_id_{counter['n']}"}
        return m

    svc.files.return_value.create.side_effect = _create
    return svc


@pytest.fixture
def _corpus(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"%PDF-1.4 a")
    (d / "b.docx").write_bytes(b"docx-b")
    (d / "c.txt").write_text("plain c")
    return d


def test_upload_directory_uploads_all(_corpus):
    svc = _make_upload_service()
    report = ds.upload_directory(_corpus, folder_id="dest", service=svc)
    assert report.dry_run is False
    assert len(report.uploaded) == 3
    assert {r.name for r in report.uploaded} == {"a.pdf", "b.docx", "c.txt"}
    assert all(r.file_id and r.file_id.startswith("new_id_") for r in report.uploaded)
    assert svc.files.return_value.create.call_count == 3


def test_upload_dry_run_touches_no_write_api(_corpus):
    svc = _make_upload_service()
    report = ds.upload_directory(_corpus, folder_id="dest", service=svc, dry_run=True)
    assert report.dry_run is True
    assert all(r.status == "dry-run" for r in report.results)
    assert all(r.file_id is None for r in report.results)
    # create() is the only write API — it must never be called on a dry run
    svc.files.return_value.create.assert_not_called()


def test_upload_skips_existing_by_name(_corpus):
    svc = _make_upload_service(existing=[{"id": "old_a", "name": "a.pdf"}])
    report = ds.upload_directory(_corpus, folder_id="dest", service=svc)
    skipped = {r.name for r in report.skipped}
    uploaded = {r.name for r in report.uploaded}
    assert skipped == {"a.pdf"}
    assert uploaded == {"b.docx", "c.txt"}
    # the skipped result carries the pre-existing file_id
    assert next(r for r in report.skipped).file_id == "old_a"
    assert svc.files.return_value.create.call_count == 2


def test_upload_respects_glob(_corpus):
    svc = _make_upload_service()
    report = ds.upload_directory(_corpus, folder_id="dest", service=svc, glob="*.pdf")
    assert {r.name for r in report.uploaded} == {"a.pdf"}


def test_upload_single_file(_corpus):
    svc = _make_upload_service()
    report = ds.upload_directory(_corpus / "b.docx", folder_id="dest", service=svc)
    assert len(report.uploaded) == 1
    assert report.uploaded[0].name == "b.docx"


def test_upload_raises_when_folder_missing(monkeypatch, _corpus):
    monkeypatch.delenv("DRIVE_FOLDER_ID", raising=False)
    with pytest.raises(RuntimeError, match="folder_id"):
        ds.upload_directory(_corpus, service=_make_upload_service())


def test_upload_raises_when_src_missing(tmp_path):
    with pytest.raises(RuntimeError, match="source path not found"):
        ds.upload_directory(tmp_path / "nope", folder_id="dest", service=_make_upload_service())


def test_upload_scope_is_drive_file():
    assert ds.UPLOAD_SCOPE.endswith("drive.file")
