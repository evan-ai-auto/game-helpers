"""CLI for validating 梦幻西游 instance/character discovery."""

from __future__ import annotations

import argparse

from ..core.window import find_window
from .accounts import scan_game_accounts


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan 梦幻西游 WSGAME instances")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    args = parser.parse_args()

    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2

    result = scan_game_accounts(parent.hwnd)
    print(f"parent hwnd={result.parent_hwnd}")
    print(f"WSGAME instances={len(result.accounts)}")
    for account in result.accounts:
        status = "logged_in" if account.logged_in else "not_logged_in"
        print(
            f"#{account.view_index} hwnd={account.hwnd} pid={account.process_id} "
            f"status={status} character={account.character_name!r} "
            f"account={account.account_name!r} identity={account.identity!r} "
            f"title={account.metadata.get('title')!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
