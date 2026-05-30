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
