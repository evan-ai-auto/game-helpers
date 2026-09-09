# Runtime User Intervention Workflow

The runtime now treats an unknown blocking state as a terminal halt for the current run.

## Contract

```text
RUNNING
  -> unknown blocking state
  -> PAUSED_USER_REQUEST
  -> checkpoint persisted
  -> current run performs no more work
```

After `PAUSED_USER_REQUEST`:

- no automatic retry
- no recovery action
- no additional capture
- no additional planning
- no input action
- calling `step()` again raises the same `RuntimePaused` checkpoint

The intended development loop is:

```text
Run -> Stop -> inspect -> provide real material -> patch code/assets -> commit/push -> start a fresh run
```

## Triggering a pause

An agent can request a halt through decision metadata:

```python
AgentDecision(
    rationale="cannot identify the current soul-task state",
    metadata={
        "pause": True,
        "pause_reason": "unknown soul-task state",
    },
)
```

A verifier can request the same halt through `VerificationResult.metadata` when an executed action has an ambiguous or unsafe outcome.

## Checkpoint

The runtime persists `data/runtime/checkpoints/latest.json` by default. The checkpoint contains:

- reason and planner rationale
- serialized game state
- current semantic observation metadata
- decision metadata
- executed action results, when any
- verification result, when any
- timestamp

Screenshot bytes are intentionally not embedded in the JSON checkpoint. Real screenshots can be supplied separately during manual diagnosis and then promoted into verified assets.

## Safety rule

A user-request halt is not a resume mechanism. Fixes are validated by starting a fresh runtime from the latest code. This keeps the manual debugging loop deterministic and prevents stale in-memory state from being mistaken for state produced by the repaired version.
