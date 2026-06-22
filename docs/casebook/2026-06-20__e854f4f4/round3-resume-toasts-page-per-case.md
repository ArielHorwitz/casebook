# Round-3 feedback: resume continuity, action feedback, page-per-case

A third batch, with decisions reached in discussion and then implemented.

## 1. Resume when the backend has no native ACP `session/load`

**Confirmed:** `claude-code-acp` reports `loadSession: false`, so for the real
Claude backend the fallback path is the *normal* resume path. The old behaviour —
a fresh, empty agent under visible-but-unremembered history — was misleading.

**Decision: lazy transcript replay.** ACP offers no rehydration beyond
`session/load`, so the only protocol-pure option is to feed the prior transcript
back as text. We do it lazily:

- On resume of a non-loadable backend, casebook stores a rendered transcript and
  **prepends it to the user's next message** — attached to the agent's turn but
  kept out of the visible bubble (the real history is already shown above).
- Resume emits a **visible notice** so the user knows the context changed and is
  imperfect (`AgentSession.send` grew a `display_text` param to separate what the
  agent receives from what the UI shows; `resume()` returns whether it loaded
  natively). Tool calls / file edits are not replayed — the framing tells the
  agent to re-read files as needed.
- Native `session/load` is still used whenever the backend supports it.

## 2. No feedback when an action silently drops

**Decision: toast notifications** (disabling buttons isn't enough for a
keyboard-driven user). Sending while the WebSocket is closed now toasts, and
`notice` events with no live session pane (failed agent starts, case-level
messages) — previously dropped — surface as toasts. A richer "log" page is noted
as a possible later addition.

## 3. Multiple cases open at once

**Decision: a dedicated page per case, not in-app tabs.** Each case is its own URL
(`/case/<id>`); the home page (`/`) is the cases list. The browser's own tabs
provide the multiplexing, and the home page can stay open separately. Both routes
are served by the same document, which routes on `location.pathname`.

- A case page scopes its WebSocket events to its own case, puts that case's files
  in the sidebar (where the case list sits on home), and shows its sessions.
- Case-list entries are real `<a href="/case/...">` links, so ctrl/middle-click
  opens a case in a new browser tab.
- `focus next/prev` stay context-constant — between cases on home, between session
  panes on a case page — and `open_focused` (Enter) opens the focused case.

This was mostly a presentation change: the engine already kept every case's
sessions alive simultaneously.
