# Multi-character task control

The runtime separates **task configuration** from **execution sessions**.

## Control-plane model

```text
Task Creation UI
      |
      v
TaskRegistry <---- CharacterRegistry
      |                  |
      +--------+---------+
               v
        CharacterScheduler
               |
               v
        CharacterSession
               |
               v
          AgentRuntime
```

- `CharacterRuntimeState` is the authoritative live context for each logged-in character.
- `TaskAssignment` records a user-created task type, selected characters, run mode, and configuration.
- `CharacterSession` is the actual execution instance for one character.
- A character has at most one active assignment/session.
- A new task-creation flow reads `CharacterRegistry`; it does not depend on a previous session object.

This means a first task can run while the user opens `+ 创建新任务` and creates another task. The second flow can show every character's current task/session/status from the shared registry.

## Conflict rule

Task queues are intentionally not implemented yet.

If a selected character already has an active task, the UI must offer exactly two choices:

1. **保持原有任务** — leave the existing assignment/session untouched for that character; the new task is not assigned to that character.
2. **新任务覆盖** — safely stop the character's current session, release its current assignment, then create the new session for the new task.

Other characters in the same new task are not affected by the conflict decision.

Example:

```text
Task #001: A,B -> 命魂

Create Task #002: B,C -> 抓鬼

B: conflict -> 保持原有任务 / 新任务覆盖
C: can start 抓鬼 independently
```

An overwrite changes only the conflicting character's active work. It does not stop A's session.

## Run mode

`RunMode.FOREGROUND` and `RunMode.BACKGROUND` are currently configuration/presentation choices only. They must not create separate foreground implementations.

The technical contract remains background-capable capture/input/vision/runtime. This keeps foreground display selection from coupling Agent, Vision, Task Executor, or Game Adapter code to a foreground-only implementation.

## Control operations

The runtime exposes character/session-scoped controls:

- `stop_character(character_id)` — stop only that character.
- `stop_session(session_id)` — stop the specific execution instance.
- `stop_all_sessions()` — safely stop every active character session.

Stopping a character clears its active assignment/session in the current control-plane state. Persistent state/logging can be layered onto these operations as execution reporting is implemented.
