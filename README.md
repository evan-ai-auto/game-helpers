# Game Helpers

## General GUI Agent Core for AI Game Agents

Game Helpers is evolving into a **General GUI Agent Core**, with AI game automation as the first application scenario.

The project is designed to build an agent capable of interacting with a graphical environment through a complete closed loop:

```
Perception
    ↓
State Understanding
    ↓
Planning
    ↓
Action Execution
    ↓
Verification
    ↓
Recovery / Memory
```

The first implementation targets one specific game environment. The game is the proving scenario; the reusable GUI Agent Core is the long-term architecture.

---

## Project Architecture

```
Platform Layer
    |
    |-- Window Management
    |-- Screen Capture
    |-- Input Execution

GUI Agent Core
    |
    |-- Vision
    |-- State Model
    |-- Action System
    |-- Verification

Game Adapter
    |
    |-- Game State
    |-- Game Rules
    |-- Available Actions

Agent Runtime
    |
    |-- Planning
    |-- Memory
    |-- Recovery

Game AI Agent
```

---

## Current Development Goal

Build a closed-loop AI game agent prototype:

```
Observe Game Screen
        ↓
Understand Current State
        ↓
Select Action
        ↓
Execute Action
        ↓
Verify Result
```

The goal is not a script collection. The goal is an autonomous agent architecture.

---

## Core Principles

### 1. Separate Core From Game Logic

The GUI Agent Core provides capabilities:

- Capture screen information
- Execute deterministic actions
- Track sessions and views
- Maintain structured state

The game adapter provides:

- Game-specific perception
- Game state definitions
- Game actions
- Validation rules

---

### 2. State First, Action Second

The agent should reason from structured state instead of directly operating on pixels.

Example:

```
Screenshot
    ↓
Vision Processing
    ↓
Game State
    ↓
Agent Decision
    ↓
Action
```

---

## Target Modules

Expected future structure:

```
src/game_helpers/

core/
    window.py
    session.py
    view.py
    interfaces.py

capture/
    screen.py
    frame.py

vision/
    detector.py
    ocr.py
    extractor.py

state/
    models.py
    tracker.py

actions/
    executor.py

agent/
    planner.py
    memory.py
    recovery.py

games/
    target_game/
        state.py
        perception.py
        actions.py
```

---

## Development Roadmap

### Phase 1 - Core Stabilization

- Preserve existing window/capture/action abstractions
- Clean project structure
- Define stable interfaces

### Phase 2 - Perception

- Add vision processing
- Convert screenshots into structured information

### Phase 3 - Game Adapter

- Support the first target game
- Define game state and actions

### Phase 4 - AI Agent

- Add planning
- Add memory
- Add recovery
- Run autonomous loops

---

## Documentation

Project architecture and migration rules are maintained in:

```
docs/PROJECT_CONTEXT.md
```

This document is the reference for future development decisions.
