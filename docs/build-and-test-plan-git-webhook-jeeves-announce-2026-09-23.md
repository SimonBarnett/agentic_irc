# Build/test plan: git webhook → Jeeves announce (park-only)

1. Read this FR. Do not implement until Simon says go.
2. When dispatched: extend `bobcallback` (or sibling path) for git
   payloads; Jeeves announces; keep `/bob/v1/report` digest path.
3. Tests without live GitHub. No secrets. No UAT.
