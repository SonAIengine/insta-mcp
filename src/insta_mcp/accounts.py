"""Account management CLI.

    python -m insta_mcp.accounts list
    python -m insta_mcp.accounts add <name> --username <id> [--proxy <url>]   # password prompted
    python -m insta_mcp.accounts check <name>                                 # login + profile
    python -m insta_mcp.accounts remove <name>
"""

import argparse
import getpass
import json
import sys

from insta_mcp.client import get_client, list_accounts, remove_account, save_account


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="insta-accounts", description="Manage Instagram accounts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List registered accounts")

    p_add = sub.add_parser("add", help="Register or update an account (password prompted)")
    p_add.add_argument("name")
    p_add.add_argument("--username", required=True)
    p_add.add_argument("--proxy", default=None, help="Per-account proxy URL (recommended)")

    p_check = sub.add_parser("check", help="Log in and print profile summary")
    p_check.add_argument("name")

    p_rm = sub.add_parser("remove", help="Remove a named account's credentials and session")
    p_rm.add_argument("name")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(json.dumps(list_accounts(), ensure_ascii=False, indent=2))
    elif args.cmd == "add":
        password = getpass.getpass(f"Password for {args.username}: ")
        if not password:
            print("Empty password, aborted", file=sys.stderr)
            return 1
        save_account(args.name, args.username, password, args.proxy)
        print(f"Saved account {args.name!r} ({args.username})")
    elif args.cmd == "check":
        cl = get_client(args.name)
        info = cl.user_info(cl.user_id)
        print(f"OK {args.name}: @{info.username} followers={info.follower_count} posts={info.media_count}")
    elif args.cmd == "remove":
        remove_account(args.name)
        print(f"Removed account {args.name!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
