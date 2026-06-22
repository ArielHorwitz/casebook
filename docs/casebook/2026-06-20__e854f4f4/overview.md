# Feedback triage for initial casebook implementation

Triage and prioritization of user feedback from the initial implementation
(commit `567aedbe27e0`).

> **Status: all items implemented** (branch `feat/casebook`, atomic commits). See
> [post-feedback-implementation-summary.md](post-feedback-implementation-summary.md)
> for what shipped and the design decisions. The triage below is retained as the
> original analysis.
>
> **Round-2 feedback** (naming model, model granularity, hotkeys) and the
> reaffirmed ACP-only constraint are tracked in
> [round2-feedback-naming-model-hotkeys.md](round2-feedback-naming-model-hotkeys.md).
> Note: explicit opus-4.8-vs-4.6 selection is **not possible through ACP** when the
> backend only advertises coarse models — recorded there.
>
> **Round-3 feedback** (lazy transcript replay on resume, toast notifications,
> a dedicated page per case) is tracked in
> [round3-resume-toasts-page-per-case.md](round3-resume-toasts-page-per-case.md).
>
> **Round-4 feedback** (two-row session header, no agent query on session start
> with the directive prepended to the first message, markdown file previews with
> Esc-to-close) is tracked in
> [round4-bootstrap-and-ui-polish.md](round4-bootstrap-and-ui-polish.md).

## Feedback items

Each item is categorized by area and assigned a priority tier.

### Tier 1 — Foundational changes

These items change core assumptions of the app and should be addressed first,
since other work builds on top of them.

#### 1. Persistent, resumable sessions (storage)

> all sessions should be stored to disk and should be resumable. i would argue
> that seeing this list of sessions is more important than the list of case
> files.

Currently sessions are in-memory only (`SessionManager` holds `AgentSession`
objects with no persistence). This is the single biggest gap — without it,
closing the browser or restarting the server loses all conversation history.

**Scope:**
- Define a session storage format (likely TOML metadata + JSONL transcript).
- Persist session state on every event (or at turn boundaries).
- Load sessions on startup; allow resuming a session from the UI.
- Rethink the sidebar: sessions should be the primary view within a case, not
  the file list.

**Considerations:**
- ACP session resumption may or may not be supported by all backends. Need to
  check whether the ACP protocol has a resume/reconnect mechanism or whether
  we'd need to replay the transcript. This is a significant unknown.
- The file-watching panel can remain but should be secondary.

#### 2. Config location (`~/.config/casebook/`)

> configs should be in `~/.config/casebook/config.toml` or similar.

Currently backend config lives in `.casebook/backends.toml` (project-local).

**Scope:**
- Move config to `~/.config/casebook/config.toml` (respecting `$XDG_CONFIG_HOME`).
- The project-local `.casebook/` directory may still be useful for per-project
  overrides, but the global config should be the primary one.

### Tier 2 — UX improvements

These improve the day-to-day experience and can be tackled once Tier 1 is
stable.

#### 3. Markdown rendering for model responses

> rendering the markdown of the model's response is super important.

Currently the frontend (`app.js`) renders messages as plain text. Model
responses are markdown and should be rendered as such.

**Scope:**
- Integrate a lightweight markdown renderer in the frontend (e.g., `marked` or
  `markdown-it`, served as a vendored script — no build toolchain).
- Apply to agent message bubbles only (user messages can stay plain).

#### 4. Session naming (manual and model-generated)

> i want to be able to name sessions manually (currently just "Agent N") as
> well as have a button "name session" which will use the model to name the
> session. the (system) prompt for this query should be configurable — i really
> dont like how claude code names sessions.

**Scope:**
- Add a session name field editable inline in the UI.
- Add a "name session" button that sends a separate (non-conversational) prompt
  to the model asking it to name the session based on the transcript.
- Make the naming prompt configurable in `config.toml`.

#### 5. "Always allow" permission mode

> i want to enable an "always allow" option for permissions. i am used to using
> "auto mode" in claude code, but i suspect that is actually more intricate
> than "always allow".

Currently permission requests are shown inline and block the agent until the
user responds.

**Scope:**
- Add a per-session or global "always allow" toggle.
- When enabled, auto-resolve all permission futures with `allow`.
- This is intentionally simpler than Claude Code's auto-mode (no classifier).
  The user accepts full responsibility.

#### 6. Start new sessions from the UI (not CLI)

> i dont think i'm interested in the original cli commands. we should be able
> to start new sessions from the ui.

The CLI currently has `init`, `new`, `list`, `show`, `preamble`, `serve`.
The user wants case creation and management to happen in the browser.

**Scope:**
- Add a "new case" flow in the web UI.
- Keep the CLI commands for scripting/automation, but the UI should be
  self-sufficient for everyday use.

### Tier 3 — Simplifications

These remove unnecessary complexity. They're easy wins but lower impact.

#### 7. Drop the `intro.md` requirement

> the idea of the `intro.md` should probably be reconsidered and instead we can
> suggest to the user at the start of a new case to fill in an `intro.md` and
> possibly other documents. for now, we can just forget the `intro.md`.

Currently `casebook new` opens an editor for the user to write `intro.md`.

**Scope:**
- Stop requiring/creating `intro.md` on case creation.
- Optionally suggest the user create one, but don't enforce it.
- Existing `intro.md` files remain valid and agents can still read them.

#### 8. Inline the `agents.md` directive into system instructions

> the `casebook/agents.md` directive that was placed on-disk in the casebook
> dir should probably just be inserted into the system instructions. we
> therefore also don't need a preamble.

Currently the preamble tells the agent to read `agents.md` from disk. This adds
a round-trip (the agent reads the file on its first turn).

**Scope:**
- Include the directive content directly in the system prompt or preamble text,
  rather than pointing the agent at a file.
- Simplify or remove the preamble template since the directive is now inline.
- The `agents.md` file can remain on disk for human reference but is no longer
  part of the agent bootstrapping flow.

### Tier 4 — Low priority

Not blocking day-to-day use; address when convenient.

#### 10. Model selection per session (added after initial triage)

> i want to be able to select models as well, particularly i prefer to work
> with opus 4.8 over opus 4.6.

ACP already supports this: `new_session` returns the backend's advertised model
list (`SessionModelState` with `available_models` + `current_model_id`), and
`set_session_model(model_id, session_id)` switches it.

**Scope:**
- Surface the advertised model list in the UI and let the user pick one per
  session (calls `set_session_model`).
- Allow a configured default model preference in `config.toml`, applied at
  session start when the backend advertises a matching model.

#### 9. Explicit backend installation (no auto-npx)

> i don't like the idea of auto-fetching-and-running npx for the backend.
> backends should be installed explicitly. we can have a builtin "echo" backend
> in case no other is available.

Currently `config.py::select_backend()` falls back to
`npx -y @zed-industries/claude-code-acp` if `claude-code-acp` isn't on PATH.
This should be removed.

**Scope:**
- Remove the npx fallback from `select_backend()`.
- Add a simple built-in "echo" backend that reflects messages back (useful for
  development and testing without a real model).
- If no backend is configured and none is on PATH, use echo and inform the user.

## Dependency graph

```
Tier 1 (foundations):
  [2. Config location] ──→ [1. Persistent sessions]
                                    ↑
Tier 2 (UX):                       │
  [3. Markdown rendering]  (independent)
  [4. Session naming]      (depends on 1)  ─┘
  [5. Always allow]        (independent)
  [6. New sessions from UI] (independent, but benefits from 1)

Tier 3 (simplifications):
  [7. Drop intro.md]       (independent, easy)
  [8. Inline agents.md]    (independent, easy)

Tier 4 (low priority):
  [9. Explicit backends]   (independent, not blocking)
```

## Suggested execution order

1. **Config location** — small foundational change
2. **Drop intro.md + inline agents.md** — quick simplifications, reduce moving parts
3. **Markdown rendering** — high-visibility UX win, independent
4. **Persistent sessions** — largest item, core architecture change
5. **Always allow permissions** — straightforward once session model is stable
6. **Session naming** — depends on persistent sessions
7. **New sessions from UI** — additive
8. **Start new cases from UI** — additive
9. **Explicit backends + echo backend** — not blocking, address when convenient
