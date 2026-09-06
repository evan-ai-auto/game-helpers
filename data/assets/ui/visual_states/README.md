# Visual state assets

Prefer resolution-scoped profiles:

`data/assets/ui/resolutions/{WxH}/*.json`

Legacy files under this folder may be marked `deprecated` / `failed`.

Each profile still declares anchors as:

- `floating`: search the full frame
- `fixed`: search near normalized `expected_x` / `expected_y`

Also carry `verification_status` (`pending` | `verified` | `failed`). See `docs/maintain.md`.
