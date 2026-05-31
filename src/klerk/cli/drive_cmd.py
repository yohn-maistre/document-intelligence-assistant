"""`klerk drive` — direct CLI access to the Drive incremental sync.

The same primitive is reachable via POST /ingest?source=drive on the FastAPI
surface; this verb is for operator convenience (manual reconciliation,
inspection of the manifest).
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def sync_cmd(
    folder_id: Annotated[
        str | None,
        typer.Option("--folder-id", help="Override DRIVE_FOLDER_ID env."),
    ] = None,
) -> None:
    """Bootstrap-or-incremental sync the Drive folder to data/drive/."""
    from klerk.drive.sync import sync as drive_sync

    try:
        report = drive_sync(folder_id=folder_id)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    mode = "bootstrap" if report.bootstrap else "incremental"
    table = Table(
        title=f"Drive sync · {mode} · folder={report.folder_id}",
        border_style="green",
        show_header=False,
    )
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("added", str(len(report.diff.added)))
    table.add_row("changed", str(len(report.diff.changed)))
    table.add_row("removed", str(len(report.diff.removed)))
    table.add_row("downloaded", str(len(report.downloaded)))
    table.add_row("download_dir", report.download_dir)
    table.add_row("page_token (next)", report.page_token[:16] + "…")
    console.print(table)

    if not report.diff.empty:
        console.print(
            Panel.fit(
                f"Next: ingest the downloaded files →\n"
                f"  [cyan]klerk index build --src {report.download_dir} --rebuild[/cyan]\n"
                f"or via the API:\n"
                f"  [cyan]POST /ingest {{source: 'path', path: '{report.download_dir}'}}[/cyan]",
                border_style="dim",
            )
        )


def upload_cmd(
    src: Annotated[
        str,
        typer.Option("--src", help="Local file or directory to upload."),
    ],
    to: Annotated[
        str | None,
        typer.Option("--to", help="Destination Drive folder ID (defaults to DRIVE_FOLDER_ID)."),
    ] = None,
    glob: Annotated[
        str,
        typer.Option("--glob", help="Glob for directory uploads (e.g. '*.pdf')."),
    ] = "*",
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing/--no-skip-existing", help="Skip files already in the folder."),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print what would upload; touch no Drive write API."),
    ] = False,
) -> None:
    """Upload a corpus directory (or single file) into a Drive folder.

    Uses the narrow `drive.file` scope, so the Service Account can only see and
    write its own uploads. Run with `--dry-run` first to preview the plan.
    """
    from klerk.drive.sync import upload_directory

    try:
        report = upload_directory(
            src,
            folder_id=to,
            glob=glob,
            skip_existing=skip_existing,
            dry_run=dry_run,
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    mode = "DRY-RUN (no writes)" if dry_run else "upload"
    title_color = "yellow" if dry_run else "green"
    table = Table(
        title=f"Drive {mode} · folder={report.folder_id}",
        border_style=title_color,
        show_header=True,
    )
    table.add_column("status", style="dim")
    table.add_column("name")
    table.add_column("file_id", style="dim")
    if not report.results:
        console.print(f"[yellow]No files matched src={src} glob={glob}[/yellow]")
        return
    for r in report.results:
        table.add_row(r.status, r.name, r.file_id or "—")
    console.print(table)

    n_up = len(report.uploaded)
    n_skip = len(report.skipped)
    n_dry = sum(1 for r in report.results if r.status == "dry-run")
    if dry_run:
        console.print(
            Panel.fit(
                f"[yellow]Dry run:[/yellow] {n_dry} file(s) would upload, "
                f"{n_skip} already present.\n"
                f"Re-run without [cyan]--dry-run[/cyan] to upload.",
                border_style="dim",
            )
        )
    else:
        console.print(f"[green]Uploaded {n_up}[/green] · skipped {n_skip}")


def status_cmd() -> None:
    """Show the persisted manifest and page-token snapshot."""
    from klerk.drive.sync import load_manifest, load_page_token, manifest_path, page_token_path

    manifest = load_manifest()
    token = load_page_token()

    table = Table(title="Drive sync state", border_style="cyan", show_header=False)
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("manifest", str(manifest_path()))
    table.add_row("manifest_files", str(len(manifest)))
    table.add_row("page_token", str(page_token_path()))
    table.add_row("page_token_value", token[:16] + "…" if token else "[yellow]not seeded[/yellow]")
    console.print(table)
