# Visual state assets

Visual assets declare their spatial behavior explicitly:

- `floating`: the feature may appear at different screen positions; detection searches the full frame.
- `fixed`: the feature is expected near a configured normalized position; detection only searches within the configured tolerance window.

This property belongs to the visual asset/anchor definition so new UI assets can reuse the same detector without adding task-specific logic.
