"""CLI viewer for who's tried the game — registrations and logins.

Deliberately not a web page: it'd otherwise expose every player's email to
anyone else who's logged in. Run it locally (or over SSH on the host):

    uv run python -m jungle_beans_game.view_log
    uv run python -m jungle_beans_game.view_log --limit 50
"""

from __future__ import annotations

import argparse

from . import db


def main() -> None:
    parser = argparse.ArgumentParser(description="View the Jungle Beans access log")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    rows = db.access_log(limit=args.limit)
    if not rows:
        print("No access log entries yet.")
        return

    print(f"{'When (UTC)':<26} {'Event':<10} {'Email':<30} IP")
    print("-" * 80)
    for row in rows:
        print(f"{row['at']:<26} {row['event']:<10} {row['email']:<30} {row['ip_address'] or ''}")


if __name__ == "__main__":
    main()
