# UI assets by client resolution

Layout:

```text
data/assets/ui/resolutions/
  800x600/          # current development baseline
  1024x768/         # placeholder — add & verify later
  …
```

Each resolution folder holds that size’s templates, click coords, and profile JSON.
Runtime selects the folder from the **current WSGAME client size**. Missing folder/file → explicit error (no silent cross-resolution reuse).

**Now:** finish and verify all features on **800×600** only.  
**Later:** you supply other resolution assets and we mark `verification_status` per folder.
