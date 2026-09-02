# Game Helpers

AI-driven game GUI automation assistant for authorized testing and personal game automation scenarios.

## Project direction

The project is being built incrementally around a perception → state → planning → action → verification loop:

- Window discovery and capture
- UI/OCR perception
- Structured game state
- Deterministic action execution
- Task/workflow engine
- AI agent planning and recovery

The first milestone is a safe, testable Windows GUI automation core. Game-specific adapters should be added only where automation is permitted.
