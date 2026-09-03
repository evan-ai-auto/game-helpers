"""Discovery of 梦幻西游 hosted game instances and character identities."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from ..core.game_view import discover_game_views
from .models import AccountCandidate


GAME_TITLE = "梦幻西游 ONLINE"
_LOGGED_IN_RE = re.compile(r"^梦幻西游 ONLINE\s+-\s+\((?P<details>.+)\)$")


@dataclass(frozen=True)
class AccountScanResult:
    """Snapshot of the hosted 梦幻西游 instances."""

    parent_hwnd: int
    accounts: tuple[AccountCandidate, ...]


def parse_character_title(title: str) -> tuple[str | None, str | None, bool]:
    """Parse the known 梦幻西游 title convention.

    The plain ``梦幻西游 ONLINE`` title is treated as an unlogged-in view.
    A logged-in title currently looks like::

        梦幻西游 ONLINE - (区服 - 角色名[角色ID])

    The parser deliberately returns conservative results: an unexpected title
    shape is not treated as proof that a character is logged in.
    """
    normalized = title.strip()
    if normalized == GAME_TITLE:
        return None, None, False

    match = _LOGGED_IN_RE.match(normalized)
    if not match:
        return None, None, False

    details = match.group("details").strip()
    if " - " not in details:
        return None, None, False

    account_name, character_part = details.rsplit(" - ", 1)
    character_name = character_part.strip()
    character_name = re.sub(r"\[[^\[\]]+\]$", "", character_name).strip()
    account_name = account_name.strip()
    if not character_name:
        return None, account_name or None, False
    return character_name, account_name or None, True


def scan_game_accounts(parent_hwnd: int) -> AccountScanResult:
    """Discover all WSGAME children and classify their title identity."""
    if sys.platform != "win32":
        raise RuntimeError("梦幻西游 account scanning requires Windows")

    import ctypes

    user32 = ctypes.windll.user32
    accounts: list[AccountCandidate] = []
    for index, view in enumerate(discover_game_views(parent_hwnd), start=1):
        character_name, account_name, logged_in = parse_character_title(view.window.title)
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(view.hwnd, ctypes.byref(process_id))
        accounts.append(
            AccountCandidate(
                view_index=index,
                hwnd=view.hwnd,
                process_id=int(process_id.value) or None,
                character_name=character_name,
                account_name=account_name,
                logged_in=logged_in,
                metadata={"title": view.window.title},
            )
        )

    return AccountScanResult(parent_hwnd=parent_hwnd, accounts=tuple(accounts))
