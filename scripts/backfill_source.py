"""One-off: record the ``Source`` property on entries collected before it existed.

Historical rows do not store which collector produced them, so the value is
inferred by :func:`mimir.notion.infer_source` — exact for arXiv, GitHub and
量子位 (each links only to its own host) and, for Hacker News, resting on the
entry type, because HN stores the external article URL.

Every row it would change is printed first. Nothing is written without
``--apply``, and those writes go to the live Notion Entries database — so
``--apply`` asks for confirmation before it starts, unless ``--yes`` says the
answer is already known.

    python scripts/backfill_source.py                  # dry run
    python scripts/backfill_source.py --apply          # ~18 min for 3200 rows
    python scripts/backfill_source.py --apply --limit 50
    python scripts/backfill_source.py --apply --yes    # unattended
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter

from mimir import config as config_module
from mimir.notion import NotionStore, infer_source
from mimir.report import _pr, _tl, _tp

log = logging.getLogger("backfill_source")


def _row_count(value: str) -> int:
    """``--limit``, refusing negatives.

    ``pending[:-1]`` is what a negative limit used to mean: a run that reported
    the full count and then silently wrote all but the last row.
    """
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more (0 = all), got {count}")
    return count


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--config", default="mimir.toml", help="config file path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to Notion (default is a dry run that writes nothing)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the writes --apply would make, without being asked",
    )
    parser.add_argument("--limit", type=_row_count, default=0, help="stop after N rows (0 = all)")
    return parser.parse_args(argv)


def _confirmed(count: int) -> bool:
    """Ask before a bulk write to the live database.

    There is no undo: the value this writes is a guess dressed as a stored fact,
    and the only way back is remembering which rows changed. So the default has
    to be to stop, and a script with no terminal to answer on has to say so
    rather than assume.
    """
    if not sys.stdin.isatty():
        log.error("--apply writes to the live database and needs confirming, but stdin "
                  "is not a terminal; pass --yes if that is really what you want")
        return False
    answer = input(f"Write Source to {count} rows in the live Entries database? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def _fetch_all(store: NotionStore) -> list[dict]:
    ds_id = store._get_data_source_id()
    pages: list[dict] = []
    cursor: str | None = None
    while True:
        store._rate_limit()
        params: dict = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = store.client.data_sources.query(ds_id, **params)
        pages.extend(resp.get("results", []))
        cursor = resp.get("next_cursor")
        if not cursor:
            return pages


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = config_module.load(args.config)
    store = NotionStore(cfg.notion.token, cfg.notion.entries_db_id)

    log.info("reading Entries …")
    pages = _fetch_all(store)
    log.info("  %d rows", len(pages))

    pending: list[tuple[dict, str]] = []
    labels = Counter()
    for page in pages:
        if _pr(page, "Source"):
            continue
        label = infer_source(_tp(page), _pr(page, "Link"))
        pending.append((page, label))
        labels[label] += 1

    log.info("\nalready labelled: %d", len(pages) - len(pending))
    log.info("to backfill: %d", len(pending))
    for label, count in labels.most_common():
        log.info("  %-12s %5d", label, count)

    if args.limit:
        pending = pending[: args.limit]
        log.info("  (limited to %d this run)", len(pending))

    for page, label in pending[:10]:
        log.info("  e.g. %-12s %s", label, _tl(page)[:60])
    if len(pending) > 10:
        log.info("  … and %d more", len(pending) - 10)

    if not args.apply:
        log.info("\nDry run — nothing written. Re-run with --apply to write.")
        return 0

    if not pending:
        return 0

    if not args.yes and not _confirmed(len(pending)):
        log.info("Aborted — nothing written.")
        return 0

    log.info("\nwriting %d rows (%.0f s at the client's rate limit) …", len(pending), 0.35 * len(pending))
    started = time.monotonic()
    written = 0
    for page, label in pending:
        try:
            store._rate_limit()
            store.client.pages.update(page["id"], properties={"Source": {"select": {"name": label}}})
            written += 1
        except Exception as exc:  # keep going; report the failures at the end
            log.warning("  failed on %s: %s", page["id"], exc)
        if written and written % 100 == 0:
            log.info("  %d/%d", written, len(pending))

    log.info("done: %d written in %.0f s", written, time.monotonic() - started)
    return 0 if written == len(pending) else 1


if __name__ == "__main__":
    sys.exit(main())
