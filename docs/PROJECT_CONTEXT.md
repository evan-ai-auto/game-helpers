# Game Helpers Project Context

## 1. Project Vision

Game Helpers is evolving from a Windows game automation helper into a **General GUI Agent Core with a game AI agent as the first application scenario**.

The project goal is not to build a collection of automation scripts. The goal is to build an AI agent runtime capable of:

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
Memory / Recovery
```

The first supported environment is one specific game. Game-specific logic should be implemented as an adapter layer, while the underlying GUI Agent Core remains reusable.

---

# 2. Current Project Position

The repository is currently in the infrastructure foundation phase.

Existing abstractions to preserve:

- Window discovery
- Screen capture
- Input execution
- Background interaction experiments
- Game view abstraction
- Session/task structure

These are foundation capabilities, not temporary helpers.

---

# 3. Target Architecture

```
+--------------------------------+
|        Game AI Agent            |
| Strategy / Decision / Recovery  |
+--------------------------------+
                |
+--------------------------------+
|        Agent Runtime            |
| Planning / Memory / Policy      |
+--------------------------------+
                |
+--------------------------------+
|        Game Adapter             |
| State / Rules / Actions         |
+--------------------------------+
                |
+--------------------------------+
|        GUI Agent Core            |
| Vision / State / Action          |
+--------------------------------+
                |
+--------------------------------+
|        Platform Layer            |
| Windows / Capture / Input        |
+--------------------------------+
```

---

# 4. Core Design Principles

## Capability and Strategy Separation

The Core answers:

"How can the computer see and act?"

The Agent answers:

"What should it do?"

Example:

Core:

```
capture_screen()
click()
press_key()
```

Agent:

```
Analyze current situation
Choose next action
Recover from failure
```

---

## Game Logic as Adapter

The first game can contain custom implementations, but game-specific behavior must not leak into the Core.

Preferred structure:

```
games/
    target_game/
        state.py
        perception.py
        actions.py
        rules.py
```

---

# 5. Target Modules

## Core Layer

Responsibilities:

- Window lifecycle
- Game session
- View abstraction
- State containers
- Common interfaces

## Capture Layer

Responsibilities:

- Screen capture
- Window capture
- Frame management

## Vision Layer

Responsibilities:

Convert pixels into structured information.

Example:

```
Screenshot
    ↓
Detected UI / Objects / OCR
    ↓
Game State
```

## State Layer

Maintain structured world representation.

The agent should reason from state, not raw images.

## Action Layer

Provide deterministic execution:

```
move()
click()
press_key()
wait()
verify()
```

## Agent Layer

Responsibilities:

- Planning
- Memory
- Policy
- Recovery

---

# 6. First Milestone

The first milestone is a closed-loop AI game agent prototype:

```
Game Window
    ↓
Capture Frame
    ↓
Understand State
    ↓
Choose Action
    ↓
Execute
    ↓
Verify Result
```

The objective is not full autonomous gameplay initially, but establishing a reliable perception-action-verification loop.

---

# 7. Development Roadmap

## Phase 1: Core Stabilization

- Freeze Core interfaces
- Stabilize capture
- Stabilize input execution
- Clean project structure

## Phase 2: Vision System

- UI detection
- OCR
- Object recognition
- State extraction

## Phase 3: Game Adapter

- Define game state
- Define available actions
- Define verification rules

## Phase 4: Agent Brain

- Planner
- Memory
- Recovery
- Long-running autonomous loop

---

# 8. Refactoring Rules

Keep:

- capture abstraction
- window abstraction
- action abstraction
- session/view concepts

Redesign or remove:

- temporary verification scripts
- game-specific logic inside Core
- documentation describing the project as only an assistant

---

# 9. Current Priority

Development order:

1. Freeze Core interfaces
2. Clean project documentation
3. Create Vision abstraction
4. Define GameState schema
5. Build first perception-action-verification loop
6. Add AI planning

---

# 10. Long Term Goal

The final product is:

"A reusable GUI Agent Core capable of operating a game through perception, reasoning and action, with the first implementation targeting one specific game."

The first game is the proving environment. The core architecture is the long-term product.
