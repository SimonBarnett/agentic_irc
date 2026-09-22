# Feature request: digest cursor_pools = Cursor Spending groups only

**Date:** 2026-09-22
**Repo:** SimonBarnett/agentic_irc
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/130
**Raised:** Simon #bobiverse UAT (marchhare tray)

## Problem

TipForm / digest shows **Cursor** quotas labelled **Smart Catalogue / Club Madeira / ntsa**.
Simon: those are **xAI** accounts — not Cursor Spending pools.

Docs to read (`agentic_build` skills, not invent):

- `box-usage` / `bob-fleet-tray`: Cursor Spending has **at least three** pools:
  1. **grok chat** (Sand)
  2. **high cost models**
  3. **low cost models**
  Simon: grok chat is one; there are more — RTFM Spending / `Get-CursorAgentUsage.py`.

`config/bob-seats.json` maps machines → email seats (SC / Club Madeira / ntsa). That seat map is **not** a list of Cursor quota pool names. Do not paint those seat labels as Cursor pool rows.

## LOCKED

1. `cursor_pools` / Cursor section = real Cursor Spending group bars only (grok chat / high cost / low cost as documented; add more if Spending exposes them).
2. Do **not** emit Smart Catalogue / Club Madeira / ntsa as Cursor quota entries.
3. Do not gut digest / TipForm. Sister TipForm consumer is agentic_build.
4. No UAT stamp.

## Related

- agentic_irc #81 (cursor_pools shape)
- agentic_build #151 / #152 (TipForm groups) — sister UI; Simon said this UAT complaint is **agentic_irc** wire