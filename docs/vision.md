# Casebook Rework: Document of Intention

## Vision

Casebook today is a minimal Python CLI for organizing bounded units of work
(investigations, brainstorms, features, designs) into a filesystem casebook.
Each case is a directory of free-form files plus a small metadata schema, and
the tool's job is to create, list, show, and discover cases. Agents consume the
casebook by reading its directive (`agents.md`), its per-case metadata
(`case.toml`), and the case files directly.

The rework turns casebook from a sidecar script into a **single working
surface**: a coordinator that connects the user's filesystem to a configurable
backend agent, so the user can work a case start-to-finish without jumping
between an editor and a separate agent UI (Claude Code, Codex, etc.).

The current workflow has the user running the agent in one window and casebook
in another, manually copy-pasting the generated preamble to bootstrap the agent
into a case. **The entire purpose of this rework is to dissolve that one
friction point** — the manual handoff — without otherwise changing what
casebook is or imposing new structure on how cases are worked.

## Design Principles

These are load-bearing. The rework must not violate them.

- **Minimal and non-prescriptive.** Casebook does not presume to know the best
  workflow for every case in every project. Cases stay free-form. No templates,
  no forced rhythms, no mandatory artifacts beyond the existing small schema.
  The power of the system is already latent in its simplicity; the app exposes
  it, it does not add scaffolding.
- **Filesystem is the source of truth.** Case state lives on disk — the case
  directory, `case.toml`, `intro.md`, `overview.md`, and whatever else the work
  produces. The app reflects the filesystem; it does not become a competing
  store of state.
- **Vendor-agnostic.** The user should not be locked into any single agent
  backend. Casebook calls into the agent through a protocol seam so the backend
  (Claude, a local model, another agent) can be swapped via configuration
  without casebook caring which is behind it.
- **Don't replace the user's tools.** The user's editor is already tuned to
  their preferences. Casebook coordinates between the filesystem and the agent;
  it is not an editor and should not try to be one.
- **The intelligence already exists.** Cross-case discovery, historical context,
  and orientation-by-listing are already designed into the directive and
  metadata, and the agent already uses them by reading files at runtime. The
  rework adds no new "features" here — it removes the human as the middleman.

## Architecture

- **Casebook is the orchestrator.** It owns the session, the case state, the
  preamble construction and injection, and the message loop. It is in the
  driver's seat.
- **The agent is a configurable backend behind a protocol seam.** Casebook
  speaks to the agent over a standard protocol (ACP — Agent Client Protocol — or
  an ACP-like seam) so the agent can be swapped without changing casebook.
  Casebook acts as the client; the agent is the backend it calls into.
- **Configuration over launching.** The user configures their chosen agent
  backend once. From then on, casebook connects to it directly — the user never
  opens the agent's own UI.
- **Preamble injection happens over the wire.** The preamble casebook already
  generates (see `cmd_preamble`) stops being something the user pastes and
  becomes something casebook hands to the agent at session start, along with the
  system prompt / directive. This is the core mechanical change.
- **Casebook coordinates filesystem ↔ agent.** When the agent writes to the
  case directory, casebook reflects the change in its interface. When the user
  edits a file in their own editor, casebook sees the write and the agent picks
  it up on the next turn by reading fresh. Casebook brokers this handoff.

## User Experience

- **One surface.** A focused interface: a pane showing the case structure and
  metadata (the case directory as-is), and a conversation pane for talking to
  the agent. Underneath, casebook manages the protocol connection and watches
  the filesystem.
- **Oriented on open.** Opening a case shows the at-a-glance view of what's in
  it — files, overview, status — and the agent is already bootstrapped into that
  case's context because casebook fed it the preamble over the wire. No
  copy-paste, no window-switching.
- **Edit where you like.** When the user wants to edit a file, they open it in
  their own editor. Casebook detects the write; the agent reads the updated file
  next turn. Editing and conversing are cleanly separated responsibilities.
- **Swap backends freely.** Changing the agent backend is a configuration
  change, not a rewrite of the user's workflow.

## Scope

### In scope

- A coordinator app (starting point can be a terminal UI; may evolve toward a
  web frontend) wrapped around the existing case directory model.
- An ACP (or ACP-like) client in casebook that connects to a configurable agent
  backend.
- A configuration layer for selecting and pointing at the agent backend.
- A message loop that injects the preamble/system directive at session start and
  threads agent responses back into the interface.
- Filesystem watching so agent-side and user-side file changes stay in sync and
  visible.
- Preserving and reusing the existing case model: `case.toml` schema,
  `agents.md` directive, preamble generation, list/show/new/hide/delete
  operations.

### Out of scope

- A built-in editor or any attempt to replace the user's editor.
- Templates, prescribed workflows, or enforced case structure.
- New metadata or schema beyond what already supports discovery.
- Casebook becoming a store of state separate from the filesystem.
- Vendor-specific coupling to any single agent backend.

## Division of Labour

- **Casebook** coordinates: owns the session and protocol connection, builds and
  injects the preamble, watches the filesystem, presents the case and the
  conversation.
- **The agent** reasons: reads the directive, metadata, and case files; does the
  work; writes artifacts back into the case directory; discovers other cases on
  its own initiative as it already does.
- **The user's editor** edits: any hands-on editing of case files happens here,
  unchanged from how the user already works.
- **The filesystem** is the source of truth: all durable case state lives in the
  case directory, and every other component reflects or reads it rather than
  competing with it.

## Open Questions for Implementation

- Which concrete protocol to standardize on at the seam (ACP specifically vs. an
  ACP-like internal interface), and how it maps onto the chosen agent backends.
- Whether casebook spawns and supervises the agent's lifecycle or only connects
  to an already-running agent.
- Terminal UI vs. web frontend as the first deliverable, given the coordinator
  responsibilities are the same either way.
- How session-to-case mapping is presented (e.g. one session per open case) and
  how prior session history is surfaced when reopening a case