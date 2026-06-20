# Post-feedback implementation summary

All feedback items from `intro.md` (plus the later model-selection request) have
been implemented on branch `feat/casebook`, as a sequence of atomic commits. This
file records what changed and the notable design decisions, so a future session
can pick up the context without rereading every diff.

## What shipped (by feedback item)

1. **Global config + explicit backends + echo backend.** Config moved to
   `~/.config/casebook/config.toml` (XDG-aware) with an optional project-local
   `.casebook/config.toml` overlay (`config.load_config`). The npx auto-fetch
   fallback is gone — the `claude` backend is offered only when `claude-code-acp`
   is on PATH. A committed in-tree `echo` ACP agent (`casebook/echo_backend.py`)
   is the always-available fallback, so the app runs with no model installed.

2. **Drop intro.md.** `casebook new` no longer opens an editor or writes
   `intro.md`; a case starts as just `case.toml`. Existing `intro.md` files remain
   valid and are treated as optional historical context.

3. **Inline directive / drop preamble.** The agent bootstrap turn now contains the
   full directive text inlined (`templates.system_instructions`) instead of
   pointing the agent at `agents.md`. The `preamble` CLI command and `.preamble`
   machinery were removed; the UI labels the bootstrap turn `system`.

4. **Markdown rendering.** Agent/thought/system bubbles render markdown, sanitized
   with DOMPurify (both `marked` and `DOMPurify` vendored as no-build scripts
   under `web/static/vendor/`). User messages stay verbatim.

5. **Persistent, resumable sessions.** `storage.SessionStore` persists each
   session's `meta.toml` + `transcript.jsonl` under
   `.casebook/sessions/<case>/<agent>/`. On startup the coordinator restores every
   session as a non-live "stored" session. A stored session can be **resumed**
   (ACP `session/load` when the backend supports it, else a fresh session that
   keeps the visible history and says the agent does not remember it), **closed**
   (stop subprocess, keep history), or **deleted**. The UI reorganized around a
   primary Sessions bar with a secondary collapsible Files panel.

6. **Always-allow.** Per-session toggle auto-resolves permission requests with the
   backend's allow option (prefers `allow_always`), emitting a notice. No
   classifier — deliberately simpler than Claude Code's auto-mode. Persisted in
   session meta.

7. **Session naming.** Per-session manual rename (✎) and a model-generated name
   button (✨). The naming query runs as an ephemeral one-shot
   (`engine/oneshot.py`) so it never pollutes the conversation; its instructions
   are configurable via `naming_prompt` in `config.toml`.

8. **Create cases / start sessions from the UI.** `+ case` (POST `/api/cases`,
   announced on the bus) and a backend picker beside `+ session` (GET
   `/api/backends`). The CLI is no longer required for everyday use.

9. **Model selection.** The backend's advertised model list
   (`SessionModelState`) is captured at session start/resume and surfaced as a
   per-session dropdown; switching calls `set_session_model`. A `default_model`
   config preference (loose id/name match) is applied at start. The echo backend
   gained two demo models (and enables the unstable ACP protocol) so the path is
   exercisable without a real backend.

## Notable decisions

- **Session vs agent terminology.** The UI now says "session" (the user's mental
  model); the engine keeps `agent_id` as the session identifier to limit churn.
- **Storage location.** Sessions live under the git-ignored `.casebook/` — they
  are local checkout state, not case content. Case artifacts remain the files
  agents write.
- **Resume honesty.** When a backend cannot `session/load`, resume opens a fresh
  session and explicitly tells the user the agent does not remember the history,
  rather than pretending continuity.
- **XSS.** Agent output is semi-trusted (it can quote files/web), so markdown is
  always sanitized; raw HTML is never injected.

## Verified

Each feature was exercised end-to-end against the in-tree echo backend:
persist → restart → resume → send; always-allow auto-resolution; manual + model
naming; default-model preference + per-session switching; and the `/api/backends`
and `POST /api/cases` endpoints. Not yet exercised against a real
`claude-code-acp` backend (not installed in the dev environment) — the
`session/load` resume path and real model lists should be confirmed there.
