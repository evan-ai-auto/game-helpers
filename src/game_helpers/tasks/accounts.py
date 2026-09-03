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


def parse_character_title(title: str) -> tuple[str | None, str | None, str | None, bool]:
    """Parse the title while preserving the complete identity payload.

    Returns ``(character_name, account_name, identity, logged_in)``. ``identity``
    is the exact text inside the title parentheses, e.g.
    ``北京1区[生日快乐] - 若相遇便不离[24101160]``. The character name is a
    convenience field; the complete identity is always retained separately.
    """
    normalized = title.strip()
    if normalized == GAME_TITLE:
        return None, None, None, False

    match = _LOGGED_IN_RE.match(normalized)
    if not match:
        return None, None, None, False

    identity = match.group("details").strip()
    if " - " not in identity:
        return None, None, identity, False

    account_name, character_part = identity.rsplit(" - ", 1)
    character_name = re.sub(r"\[[^\[\]]+\]$", "", character_part.strip()).strip()
    account_name = account_name.strip()
    if not character_name:
        return None, account_name or None, identity, False
    return character_name, account_name or None, identity, True


def scan_game_accounts(parent_hwnd: int) -> AccountScanResult:
    """Discover all WSGAME children and classify their title identity."""
    if sys.platform != "win32":
        raise RuntimeError("梦幻西游 account scanning requires Windows")

    import ctypes

    user32 = ctypes.windll.user32
    accounts: list[AccountCandidate] = []
    for index, view in enumerate(discover_game_views(parent_hwnd), start=1):
        character_name, account_name, identity, logged_in = parse_character_title(view.window.title)
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(view.hwnd, ctypes.byref(process_id))
        accounts.append(
            AccountCandidate(
                view_index=index,
                hwnd=view.hwnd,
                process_id=int(process_id.value) or None,
                character_name=character_name,
                account_name=account_name,
                identity=identity,
                logged_in=logged_in,
                metadata={"title": view.window.title},
            )
        )

    return AccountScanResult(parent_hwnd=parent_hwnd, accounts=tuple(accounts))
