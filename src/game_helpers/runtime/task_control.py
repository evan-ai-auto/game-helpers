"""Task creation and multi-character scheduling primitives.

A TaskAssignment is a user-level configuration.  A CharacterSession is the
runtime execution instance for one character.  A character can have only one
active assignment/session at a time; conflicting assignments are resolved by
the caller with KEEP_EXISTING or OVERWRITE.  Queues are intentionally not
implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any
from uuid import uuid4


class RunMode(str, Enum):
    """Presentation/configuration choice; implementations remain background-capable."""

    FOREGROUND = "foreground"
    BACKGROUND = "background"


class RuntimeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class AssignmentConflict(str, Enum):
    KEEP_EXISTING = "keep_existing"
    OVERWRITE = "overwrite"


@dataclass
class CharacterRuntimeState:
    character_id: str
    display_name: str
    login_status: str = "unknown"
    current_task_id: str | None = None
    current_session_id: str | None = None
    task_type: str | None = None
    status: RuntimeStatus = RuntimeStatus.IDLE
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskAssignment:
    task_id: str
    task_type: str
    character_ids: tuple[str, ...]
    run_mode: RunMode = RunMode.BACKGROUND
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class CharacterSession:
    session_id: str
    task_id: str
    character_id: str
    task_type: str
    run_mode: RunMode
    status: RuntimeStatus = RuntimeStatus.IDLE
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssignmentDecision:
    character_id: str
    accepted: bool
    conflict: bool
    reason: str
    replaced_task_id: str | None = None


class TaskRegistry:
    """Authoritative collection of user-created task assignments."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskAssignment] = {}
        self._lock = RLock()

    def create(self, task_type: str, character_ids: list[str] | tuple[str, ...], *, run_mode: RunMode = RunMode.BACKGROUND, config: dict[str, Any] | None = None, task_id: str | None = None) -> TaskAssignment:
        assignment = TaskAssignment(task_id or f"task-{uuid4().hex[:12]}", task_type, tuple(character_ids), run_mode, dict(config or {}))
        with self._lock:
            self._tasks[assignment.task_id] = assignment
        return assignment

    def get(self, task_id: str) -> TaskAssignment | None:
        with self._lock:
            return self._tasks.get(task_id)

    def all(self) -> tuple[TaskAssignment, ...]:
        with self._lock:
            return tuple(self._tasks.values())


class CharacterRegistry:
    """Authoritative runtime view used by every task-creation flow."""

    def __init__(self) -> None:
        self._characters: dict[str, CharacterRuntimeState] = {}
        self._lock = RLock()

    def register(self, character_id: str, display_name: str, *, login_status: str = "unknown", metadata: dict[str, Any] | None = None) -> CharacterRuntimeState:
        state = CharacterRuntimeState(character_id, display_name, login_status, metadata=dict(metadata or {}))
        with self._lock:
            self._characters[character_id] = state
        return state

    def get(self, character_id: str) -> CharacterRuntimeState | None:
        with self._lock:
            return self._characters.get(character_id)

    def all(self) -> tuple[CharacterRuntimeState, ...]:
        with self._lock:
            return tuple(self._characters.values())

    def available_for_assignment(self) -> tuple[CharacterRuntimeState, ...]:
        with self._lock:
            return tuple(c for c in self._characters.values() if c.current_task_id is None or c.status in {RuntimeStatus.IDLE, RuntimeStatus.STOPPED, RuntimeStatus.COMPLETED, RuntimeStatus.FAILED})


class CharacterScheduler:
    """Assigns one current task to each character; conflicts require an explicit choice."""

    def __init__(self, characters: CharacterRegistry, tasks: TaskRegistry) -> None:
        self.characters = characters
        self.tasks = tasks
        self._sessions: dict[str, CharacterSession] = {}
        self._lock = RLock()

    def assign(self, assignment: TaskAssignment, *, conflict: AssignmentConflict | None = None) -> tuple[AssignmentDecision, ...]:
        decisions: list[AssignmentDecision] = []
        with self._lock:
            for character_id in assignment.character_ids:
                character = self.characters.get(character_id)
                if character is None:
                    decisions.append(AssignmentDecision(character_id, False, False, "character_not_found"))
                    continue
                if character.current_task_id and character.current_task_id != assignment.task_id and character.status in {RuntimeStatus.RUNNING, RuntimeStatus.PAUSED, RuntimeStatus.STOPPING}:
                    if conflict is None:
                        decisions.append(AssignmentDecision(character_id, False, True, "existing_task_requires_keep_or_overwrite", character.current_task_id))
                        continue
                    if conflict is AssignmentConflict.KEEP_EXISTING:
                        decisions.append(AssignmentDecision(character_id, False, True, "kept_existing_task", character.current_task_id))
                        continue
                    old_task = character.current_task_id
                    self._stop_current(character)
                    replaced = old_task
                else:
                    replaced = character.current_task_id
                    if replaced:
                        self._stop_current(character)
                session = CharacterSession(f"session-{uuid4().hex[:12]}", assignment.task_id, character_id, assignment.task_type, assignment.run_mode, RuntimeStatus.RUNNING)
                self._sessions[session.session_id] = session
                character.current_task_id = assignment.task_id
                character.current_session_id = session.session_id
                character.task_type = assignment.task_type
                character.status = RuntimeStatus.RUNNING
                decisions.append(AssignmentDecision(character_id, True, replaced is not None, "assigned", replaced))
        return tuple(decisions)

    def _stop_current(self, character: CharacterRuntimeState) -> None:
        if character.current_session_id and character.current_session_id in self._sessions:
            self._sessions[character.current_session_id].status = RuntimeStatus.STOPPED
        character.current_task_id = None
        character.current_session_id = None
        character.task_type = None
        character.status = RuntimeStatus.STOPPED

    def stop_character(self, character_id: str) -> bool:
        with self._lock:
            character = self.characters.get(character_id)
            if character is None:
                return False
            self._stop_current(character)
            return True

    def stop_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.status = RuntimeStatus.STOPPED
            character = self.characters.get(session.character_id)
            if character and character.current_session_id == session_id:
                character.current_task_id = None
                character.current_session_id = None
                character.task_type = None
                character.status = RuntimeStatus.STOPPED
            return True

    def stop_all(self) -> None:
        with self._lock:
            for character in self.characters.all():
                self._stop_current(character)

    def sessions(self) -> tuple[CharacterSession, ...]:
        with self._lock:
            return tuple(self._sessions.values())


class MultiCharacterRuntime:
    """Control-plane facade for creating assignments and inspecting live characters."""

    def __init__(self) -> None:
        self.characters = CharacterRegistry()
        self.tasks = TaskRegistry()
        self.scheduler = CharacterScheduler(self.characters, self.tasks)

    def create_task(self, task_type: str, character_ids: list[str] | tuple[str, ...], *, run_mode: RunMode = RunMode.BACKGROUND, config: dict[str, Any] | None = None, conflict: AssignmentConflict | None = None) -> tuple[TaskAssignment, tuple[AssignmentDecision, ...]]:
        assignment = self.tasks.create(task_type, character_ids, run_mode=run_mode, config=config)
        decisions = self.scheduler.assign(assignment, conflict=conflict)
        return assignment, decisions

    def character_context(self) -> tuple[CharacterRuntimeState, ...]:
        """Return the context that a new task-creation screen should display."""
        return self.characters.all()

    def stop_character(self, character_id: str) -> bool:
        return self.scheduler.stop_character(character_id)

    def stop_session(self, session_id: str) -> bool:
        return self.scheduler.stop_session(session_id)

    def stop_all_sessions(self) -> None:
        self.scheduler.stop_all()
