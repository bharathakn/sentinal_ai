#!/usr/bin/env python3
"""Manage team accounts (these see every case).

Public sign-up on the website creates private-workspace accounts; `promote`
turns one of those into a team account.

Uses the same store as the API: SENTINEL_CASE_STORE=json (var/auth.json) or
mongodb (MONGODB_URI / MONGODB_DATABASE). Reads .env when present. To manage
the hosted accounts, run it locally with the Atlas settings.

    python scripts/manage_users.py create alice --name "Alice Rao"   # prompts for the password
    python scripts/manage_users.py reset-password alice              # signs alice out everywhere
    python scripts/manage_users.py disable alice | enable alice
    python scripts/manage_users.py promote alice                     # self-registered → team account
    python scripts/manage_users.py list

Passwords are prompted (not echoed) or read from stdin with --password-stdin;
they are never accepted as command-line arguments.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _password(args) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("New password: ")
    if getpass.getpass("Repeat password: ") != first:
        raise SystemExit("Passwords do not match.")
    return first


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(".env", override=False)
    except ImportError:
        pass
    from src.api.auth import AuthService, auth_store_from_env

    ap = argparse.ArgumentParser(description="Manage Sentinel AI analyst accounts.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("username")
    c.add_argument("--name", required=True, help="Display name shown in the dashboard and audit trail")
    r = sub.add_parser("reset-password")
    r.add_argument("username")
    for p in (c, r):
        p.add_argument("--password-stdin", action="store_true")
    for name in ("disable", "enable", "promote"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list")
    args = ap.parse_args()

    svc = AuthService(auth_store_from_env())
    try:
        if args.cmd == "create":
            u = svc.create_user(args.username, args.name, _password(args))
            print(f"Created {u.username} ({u.display_name}).")
        elif args.cmd == "reset-password":
            if svc.store.get_user(args.username.lower()) is None:
                raise SystemExit(f"No user {args.username}.")
            svc.set_password(args.username.lower(), _password(args))
            print(f"Password reset for {args.username.lower()}; existing sessions signed out.")
        elif args.cmd in ("disable", "enable"):
            svc.set_active(args.username.lower(), args.cmd == "enable")
            print(f"{args.username.lower()} {args.cmd}d.")
        elif args.cmd == "promote":
            svc.promote(args.username.lower())
            print(f"{args.username.lower()} is now a team account and can see every case.")
        else:
            for u in svc.store.list_users():
                last = u.last_login_at_utc.isoformat() if u.last_login_at_utc else "never"
                print(f"{u.username:24} {u.display_name:28} {'self-signup' if u.self_registered else 'team':11} {'active' if u.active else 'DISABLED':9} last login {last}")
    except (ValueError, KeyError) as exc:
        raise SystemExit(f"Error: {exc}")


if __name__ == "__main__":
    main()
