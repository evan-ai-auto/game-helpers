"""Character selection and stable WSGAME instance resolution for 梦幻西游."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.view_manager import GameViewManager
from .accounts import AccountScanResult, scan_game_accounts
from .models import AccountCandidate


@dataclass(frozen=True)
class CharacterSelectionResult:
    """Selected logged-in character and its concrete hosted game identity."""

    account: AccountCandidate

    @property
    def view_index(self) -> int:
        return self.account.view_index

    @property
    def hwnd(self) -> int:
        return self.account.hwnd

    @property
    def process_id(self) -> int | None:
        return self.account.process_id

    @property
    def character_name(self) -> str:
        if not self.account.character_name:
            raise RuntimeError("selected account is not a logged-in character")
        return self.account.character_name


def logged_in_accounts(result: AccountScanResult) -> tuple[AccountCandidate, ...]:
    """Return only logged-in character instances, preserving scan order."""
    return tuple(account for account in result.accounts if account.logged_in)


def select_character(result: AccountScanResult, view_index: int) -> CharacterSelectionResult:
    """Select a logged-in character by the stable WSGAME view index.

    The index is preferred over character name because two instances may host
    characters with the same visible name. The returned HWND/PID/identity are
    the concrete instance identifiers used by later task stages.
    """
    matches = [account for account in result.accounts if account.view_index == view_index]
    if not matches:
        raise ValueError(f"game view #{view_index} was not found")
    account = matches[0]
    if not account.logged_in or not account.character_name:
        raise ValueError(f"game view #{view_index} is not a logged-in character")
    return CharacterSelectionResult(account=account)


def scan_and_select(parent_hwnd: int, view_index: int) -> CharacterSelectionResult:
    """Scan current instances and select one logged-in character."""
    return select_character(scan_game_accounts(parent_hwnd), view_index)


def sync_selected_character(parent_hwnd: int, selection: CharacterSelectionResult) -> None:
    """Background-select a character and synchronize native Tab + Surface.

    This uses the MVP-2 locked sequence: switch the actual WSGAME surface first,
    then select the native tab, while requiring the user's foreground window to
    remain unchanged.
    """
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    foreground_before = _foreground_hwnd()
    manager.switch_surface_to(selection.view_index)
    manager.switch_to(selection.view_index)
    if manager.current_surface_index() != selection.view_index:
        raise RuntimeError("selected character surface is not active")
    if manager.current_index() != selection.view_index:
        raise RuntimeError("selected character native tab is not active")
    foreground_after = _foreground_hwnd()
    if foreground_after != foreground_before:
        raise RuntimeError(
            "foreground window changed while selecting character: "
            f"before={foreground_before}, after={foreground_after}"
        )


def _foreground_hwnd() -> int:
    import ctypes
    return int(ctypes.windll.user32.GetForegroundWindow())
