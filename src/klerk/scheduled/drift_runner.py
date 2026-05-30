"""APScheduler hook for the nightly drift scan.

Opt-in via the `scheduled` extra (`pip install klerk[scheduled]` or
`uv sync --extra scheduled`). Imports of `apscheduler` are deferred to
runtime so the base install stays slim.

Run modes:
  - Foreground: `python -m klerk.scheduled.drift_runner` blocks on a
    BlockingScheduler with a daily 02:00 UTC trigger.
  - One-shot:  `python -m klerk.scheduled.drift_runner --once` runs a
    single scan and exits — handy for cron-style external schedulers.

The scan writes to `.klerk/drift-events.jsonl`; the FastAPI endpoint
`GET /drift/recent` tails that file. The two paths share no state aside
from the jsonl, so the scheduler can run in a sidecar process / cron job
without coordinating with the API.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from klerk.agent.drift import scan


def run_once() -> int:
    """Run one scan, print a one-line summary to stdout, return exit code."""
    report = scan()
    iso = report.started_at.isoformat()
    if report.error:
        print(
            f"[{iso}] drift scan FAILED ({report.run_id}): {report.error}",
            file=sys.stderr,
        )
        return 1
    print(
        f"[{iso}] drift scan {report.run_id}: {len(report.events)} event(s) "
        f"across {report.n_docs_scanned} doc(s)."
    )
    return 0


def start(*, hour: int = 2, minute: int = 0) -> None:
    """Block on a BlockingScheduler firing once per day at HH:MM UTC."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "drift_runner: apscheduler not installed. Install the optional "
            "[scheduled] extra:  uv sync --extra scheduled"
        ) from e

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_once,
        CronTrigger(hour=hour, minute=minute),
        id="klerk_drift",
        replace_existing=True,
    )
    started_iso = datetime.now(timezone.utc).isoformat()
    print(f"[{started_iso}] drift scheduler started — daily {hour:02d}:{minute:02d} UTC.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="klerk-drift")
    parser.add_argument("--once", action="store_true", help="Run a single scan then exit.")
    parser.add_argument("--hour", type=int, default=2, help="Daily run hour (UTC).")
    parser.add_argument("--minute", type=int, default=0, help="Daily run minute (UTC).")
    args = parser.parse_args()
    if args.once:
        sys.exit(run_once())
    start(hour=args.hour, minute=args.minute)


if __name__ == "__main__":
    main()
