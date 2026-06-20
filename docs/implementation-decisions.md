# Casebook App: Implementation Decisions

This records the design decisions made while implementing the first version of
the casebook coordinator app, for review. It complements `vision.md` (intent)
and `architecture.md` (cross-app strategy). Decisions are grouped into UX and
technical; a final section lists known limitations and deferred work.

The three load-bearing choices were made by the user up front: **browser UI**,
**real Claude backend** (`@zed-industries/claude-code-acp`), and **multi-agent
from the start**. Everything below follows from those.

## Verified working

End-to-end against a throwaway echo agent (not committed): spawn → `initialize`
→ `new_session` → preamble injected as turn one → streamed response → user turn
→ response, with events flowing to the bus. The web server boots under uvicorn,
serves the REST + static surface, reflects new cases live from the filesystem,
and the WebSocket delivers the snapshot frame. The original CLI commands still
work.

## UX decisions

1. **No-build vanilla-JS frontend** (no React/bundler). Rationale: the minimal-
   dependencies principle; the UI is a thin reflection of engine state and does
   not justify a build toolchain. Trade-off: manual DOM code in `app.js`.
2. **Layout = case sidebar · file strip · a row of agent panes.** One pane per
   agent, side by side, so multiple agents working a case are visible at once.
   One case is open at a time; other cases' agents stay alive but hidden.
3. **The preamble is shown, not hidden** — rendered as a dimmed "preamble"
   bubble. The user sees exactly what bootstrapped each agent. Transparency over
   magic.
4. **Agent thinking and tool calls are visible.** Thoughts render muted/italic;
   tool calls render as compact chips with a live status (pending/in&nbsp;progress/
   completed/failed). The user can see what the agent is doing, not just its
   final text.
5. **Permission prompts are surfaced inline and block the agent.** When an agent
   asks permission (e.g. to use a tool), the request appears in that agent's
   transcript with the offered options plus a Deny button; the agent waits for
   the user's answer. The user stays in control of tool/filesystem access.
6. **One turn at a time per agent.** While an agent is working, its input is
   disabled and a Stop button can cancel the turn. Parallelism is *across*
   agents, not within one — matching ACP's one-turn-per-session model. A send
   that arrives mid-turn is rejected with a notice.
7. **Files are read-only in the app** (click opens a modal viewer). Casebook does
   not become an editor (vision principle). Editing happens in the user's own
   editor; the filesystem watcher reflects the change and the agent reads fresh
   next turn.
8. **Agents get default labels** ("Agent 1", "Agent 2", …) via a "+ agent"
   button. No rename UI in this cut.

## Technical decisions

1. **Package restructure.** `src/main.py` (a run-as-script CLI) became a proper
   `src/casebook/` package built with hatchling, installed via `uv`, exposing a
   `casebook` console script. Layout mirrors `architecture.md`: `engine/`
   (UI-agnostic ACP machinery), `coordinator.py` (casebook-specific policy),
   `web/` (thin surface), plus `cases.py`/`templates.py`/`config.py`/`cli.py`.
2. **Depend on the official ACP Python SDK** (`agent-client-protocol`, pinned
   `>=0.10.1`), isolated behind the engine so SDK/spec churn stays contained.
   Protocol version 1.
3. **One subprocess per agent** (its own ACP connection + single session) rather
   than one connection multiplexing many sessions. Rationale: isolation,
   independent lifecycles, and true concurrency for agents that coordinate only
   through the filesystem. Cost: one Node process per agent. Swappable later.
4. **Vendor-agnostic backend resolution.** A backend is a launch command. The
   default "claude" backend resolves to: an explicit command in
   `.casebook/backends.toml` → a `claude-code-acp` on PATH → `npx -y
   @zed-industries/claude-code-acp`. Other ACP agents are added by config.
5. **Client capabilities: filesystem yes, terminal no (for now).** We advertise
   `read_text_file`/`write_text_file` and implement them, confined to the project
   root. We do **not** yet advertise terminal support, so agent tools that need a
   terminal (e.g. shell/bash) are unavailable in this cut — acceptable for
   doc/analysis-centric cases; see limitations.
6. **Preamble injected as the first prompt turn.** ACP has no separate
   system-prompt channel, so the preamble casebook already generates is sent as
   turn one of each session. This is the mechanical change the whole rework was
   about — no more copy-paste.
7. **Full environment to the backend.** The agent subprocess receives the full
   parent environment (overlaid with any backend-specific env), not the SDK's
   trimmed MCP default — because the backend is the user's own trusted agent and
   needs its PATH and ambient Claude auth.
8. **Filesystem watching** via `watchfiles.awatch` on each open case directory,
   emitting `files_changed`. This catches both the user's editor writes and the
   agent's *direct* writes (Claude Code writes via its own tools, not only via
   ACP's fs methods), keeping the file panel honest.
9. **In-process asyncio event bus.** The engine publishes plain dict events; each
   subscriber (browser) gets its own unbounded queue; publishing never blocks on
   a slow consumer. Events are the *only* way state leaves the engine, keeping the
   UI a pure reflection.
10. **Transcripts are in-memory, not persisted.** A replayable subset (messages,
    tool calls, notices) is kept per agent so a reconnecting/reloading browser
    can catch up. They are deliberately **not** written to disk: the filesystem is
    the source of truth and the app must not become a competing store. Durable
    artifacts are the files agents write.
11. **Web transport: Starlette + uvicorn.** REST serves the cheap read-only views
    (case list/detail, file contents); a single WebSocket is the live spine
    (events out, actions in). Slow actions (spawning an agent, a prompt turn) are
    dispatched as background tasks so the socket stays responsive; progress
    returns as events.
12. **Permission round-trip via futures.** The agent's `request_permission`
    callback creates a future keyed by `request_id`, emits the prompt event, and
    awaits; the user's answer arrives over the WebSocket and resolves the future.
13. **Errors during a turn become `notice` events**, never crashing the engine.

## Known limitations / deferred (please review)

- **No terminal capability** → agent tools requiring a shell are unavailable.
  Adding it means implementing the ACP terminal methods (create/output/wait/
  kill/release). Highest-impact follow-up if cases need command execution.
- **No transcript persistence / session resume.** Stopping the server or removing
  an agent loses its transcript. ACP's `load_session`/`resume_session` could
  restore agent-side history later.
- **A pending permission request is not replayed** to a browser that reconnects
  mid-request (it isn't in the replayable set), which could leave an agent
  blocked. Small, fixable; left out of the first cut.
- **No auth flow.** We rely on the adapter using ambient Claude auth. If a
  backend requires ACP `authenticate()`, we don't handle it yet.
- **Single-user assumption.** Multiple browsers share one coordinator and all see
  all events — fine for local single-user use, not multi-tenant.
- **"Allow always" isn't cached locally.** Every permission still round-trips;
  the adapter may remember it on its side, but casebook does not.
- **Watcher scope is the open case directory only.** Agent writes elsewhere in
  the project won't appear in the file panel — by design (the panel is the case).
- **No committed tests.** The engine loop was validated with a throwaway echo
  agent. A committed stub agent + test harness is a sensible follow-up (it was
  the road not taken when you chose "real adapter" over "both").
