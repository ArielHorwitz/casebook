# Round-8 feedback: keep leftovers, 50% columns, surface usage, console status

## 1. Don't clean up trivial leftovers on startup

Reverted the startup deletion of trivial (empty, auto-named) sessions — `casebook`
no longer deletes anything on load; it restores whatever is on disk as-is. New
trivial sessions are still never written in the first place, and closing a trivial
session still discards it; only the destructive startup sweep was removed.

## 2. Default session-column width = 50%

`session_width` now defaults to `"50%"`, so two columns fill the width by default
(still configurable via `[ui]`; `session_min_width` 320px keeps it usable on
narrow screens).

## 3. Surface usage to the user

Capture what ACP provides and show it per session:

- `session/update` `usage_update` → context `used`/`size` (with a percentage) and
  optional cumulative `cost`.
- `PromptResponse.usage` → token totals.

These are merged per session, shown in the pane header, and carried in the
snapshot so a reconnecting browser sees them. (It's only as detailed as the
backend reports — the echo dev backend reports nothing; a real backend like
`claude-code-acp` reports context/cost.) Subscription / "5-hour" limits remain
**unavailable** — ACP has no such concept (see round 7).

## 4. Console activity status

The `casebook serve` process now prints to its console whenever the set of busy
sessions changes — `[casebook] N session(s) running: …` and `[casebook] all
sessions idle` — so you can glance at the terminal before Ctrl+C to see whether
anything is still working.
