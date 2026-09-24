# Build/test plan: #168 recycle after merge

1. Read issue #168 + FR doc. Implement skill/README text only unless tests need a string assert.
2. Sister mark on `agentic_build` `bob-hostile-mrb` if that repo owns merge duty (separate PR if needed).
3. Open PR linking #168. Do not push main. Do not live-recycle. No UAT.

## Checks

- `rg` recycle + ionos in the named skills.
- pytest or Test-Pack fails if the duty line is deleted.
