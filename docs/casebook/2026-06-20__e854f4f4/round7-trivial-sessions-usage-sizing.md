# Round-7 feedback: trivial sessions, ACP usage, column sizing, home hotkey

## 1. Resuming empty sessions fails → don't persist trivial sessions

A brand-new session with no messages and its auto-assigned name is identical to
not existing, and resuming such an empty session can fail on the backend. Fixed:

- A session is written to disk only once it's **non-trivial** — it has a message
  or a custom name. The first real content commits `meta.toml`, kept paired with
  the transcript.
- **Closing** a trivial session **discards** it (like delete) instead of storing
  it; closing a meaningful one still collapses it to the sidebar.
- **Startup** cleans up trivial leftovers from before this change (a `named` flag
  in `meta.toml` distinguishes a renamed-but-empty session, which is kept).

## 2. ACP usage / limits — what's possible

ACP exposes **context usage** but **not** subscription/plan limits:

- `session/update` of kind `usage_update` carries `used` (tokens currently in
  context), `size` (total context-window tokens), and an optional cumulative
  `cost`. `PromptResponse.usage` also returns per-turn token counts. So a
  context meter ("used / window") is achievable and ACP-native — casebook
  currently receives and ignores these updates.
- There is **nothing** in ACP for subscription/plan quotas, Claude's "5-hour
  session" limits, or reset times. Those are vendor-specific (a Claude
  subscription concept) and not surfaced through ACP, so casebook can't show them
  without depending on vendor internals — which it deliberately avoids.

(Surfacing the context meter is a possible follow-up, not yet built.)

## 3. Configurable session column width

Session columns (panes) are sized via a `[ui]` table — `session_width`,
`session_min_width`, `session_max_width` — served at `/api/ui` and applied as CSS
variables. Values are CSS lengths, so `vw`/`%` give a fraction of the screen and
`px`/`em` give fixed sizes; `none` disables the max. Columns don't grow/shrink to
fit; the main area scrolls horizontally when they overflow.

## 4. Home hotkey

Added a `home` hotkey (default `h`) that returns to the cases page from a case
page (mirrors the ← Cases link).

## 5. Do all sessions keep running? (answer)

Yes. Sessions are server-side subprocesses owned by the coordinator, independent
of any browser. The page-per-case UI is just a view that filters events to its
case; every case's sessions keep running regardless of which pages/tabs are open
(or whether any browser is connected at all). They stop only when you close or
delete the session, or stop the server.
