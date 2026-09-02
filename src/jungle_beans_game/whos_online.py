"""CLI viewer for who's actively playing right now.

Every logged-in API request stamps `users.last_active_at` (see
`login_required` in app.py). This just reads that back and flags anyone
recent enough as online. Deliberately not a web page, same reasoning as
view_log.py — avoids exposing player activity to anyone else logged in.

    uv run python -m jungle_beans_game.whos_online
    uv run python -m jungle_beans_game.whos_online --minutes 5
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from . import db

ONLINE_THRESHOLD_MINUTES = 2.0  # how recent an action counts as "still playing"


def _ago(iso_ts: str) -> tuple[str, float]:
    then = datetime.fromisoformat(iso_ts)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s ago", seconds
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago", seconds
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago", seconds
    return f"{int(seconds // 86400)}d ago", seconds


def main() -> None:
    parser = argparse.ArgumentParser(description="Show who's actively playing Jungle Beans")
    parser.add_argument(
        "--minutes", type=float, default=ONLINE_THRESHOLD_MINUTES,
        help=f"how recent counts as online (default: {ONLINE_THRESHOLD_MINUTES})",
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    threshold_seconds = args.minutes * 60

    rows = db.activity_status(limit=args.limit)
    if not rows:
        print("No player activity recorded yet.")
        return

    online = 0
    print(f"{'Name':<20} {'Last active':<12} Status")
    print("-" * 45)
    for row in rows:
        label, seconds = _ago(row["last_active_at"])
        is_online = seconds <= threshold_seconds
        online += is_online
        print(f"{row['name']:<20} {label:<12} {'ONLINE' if is_online else ''}")

    print()
    print(f"{online} player(s) active in the last {args.minutes:g} minute(s).")


if __name__ == "__main__":
    main()
