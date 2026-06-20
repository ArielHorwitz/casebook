# Architecture: A Shared Substrate for Agent-Interaction Tools

## Purpose

This document records how casebook relates to other agent-interaction tools we
expect to build (the first being an "adversarial debate" tool), and how to
structure the code so those tools share what they should without coupling what
they shouldn't.

It exists because of a recurring temptation: once you have more than one idea for
an app that connects a user to one or more agents, you start to fear
reimplementing the same wrapper — config, rendering, the agent connection — for
each one. This document resolves how to handle that fear without overbuilding.

`vision.md` remains the tightly-scoped intention document for the casebook
rework itself. This document is the layer above it: the multi-app strategy.

## The decision

**Build standalone apps over a shared library. Do not build a framework or a
plugin host.**

- Each tool (casebook, debate, future tools) is its own app with its own `main`,
  its own layout, and its own domain model.
- Common, app-agnostic machinery lives in a shared library that each app
  *depends on and calls into* — never a host that calls into the apps.
- Apps are **independently installable**. A second user who wants only the debate
  tool installs only the debate tool; they never acquire casebook to get it.

### Why not a plugin host / single unified app

The appeal of one unified app is "never reimplement the wrapper." But that
conflates two independent axes:

- **Code-sharing** — how much logic is shared between tools.
- **Packaging** — how many installable units there are.

A shared library gives full code-sharing *with* independent packaging. A plugin
host buys only one extra thing on top of that: a single launch point / shared
chrome at runtime. That is a UX nicety, it is the only thing genuinely in
tension, and it is trivially addable later as a thin launcher over
independently-installed tools. Committing to a host worldview up front means
every future tool must conform to assumptions made before those tools were
validated — a product in itself, built for an audience of one unvalidated
workflow.

**Guiding rule: extract a library from duplication you have felt, never a
framework from duplication you have imagined.**

## The seam: what is shared vs. per-app

The shared library knows nothing about cases or debates. It manages agents and
renders conversations; it does not know what the conversation is *for*.

### Shared (the library)

- **Backend config & selection.** Choosing and pointing at the agent backend
  (vendor-agnostic; the ACP / ACP-like seam lives here).
- **Agent-session manager** — the real prize. Spawn and track multiple agent
  sessions, route messages in and out, surface each session's state, and accept
  user turns injected into any session. This is lifecycle + I/O only. It exposes
  *sessions and messages* and knows nothing about the domain.
- **UI components** — a transcript/conversation view, a message input, an
  agent-session pane, a backend-config form. Components, **not** a page shell.

### Per-app (stays in each tool)

- **Coordination policy** — who talks when, and how the agents coordinate. This
  is deliberately *not* generalized.
- **Layout / shell** — each app composes its own page from shared components.
- **Domain model** — cases, debates, their on-disk shape and metadata.

### Why these boundaries

- **Component-level UI, not shell-level.** Encapsulating a whole app shell would
  bake in one tool's layout (e.g. casebook's case-browser-plus-conversations) and
  the next tool would fight it. Each app composes its own layout from shared
  widgets. Expected first UI target is browser-based.
- **The session manager stays dumb.** Lifecycle and I/O are genuinely common;
  coordination is genuinely not. Keeping the manager ignorant of coordination is
  what lets two very different tools share it.

## The two reference workloads

Both tools are multi-agent, keep the user in the loop, and are deliberately
non-prescriptive (neither presumes to dictate the best workflow universally).
They differ in exactly one place — coordination — and that difference is what
the per-app layer absorbs.

| | Casebook | Debate |
|---|---|---|
| Agents | Multiple, on different parts of a case | Multiple (e.g. challenger, defender, judge) |
| User | In the loop, steering | In the loop, interjecting to clarify/steer |
| Prescriptive | No | No |
| **Coordination** | **Mostly-independent workers that sync through the filesystem** | **Structured dialogue — one agent's output is another's input** |

**Casebook explicitly does not need structured inter-agent coordination.** Its
agents work in parallel and synchronize through the filesystem, which is its
source of truth. This is a deliberate constraint, and it is what keeps the shared
session manager simple: filesystem-sync coordination needs nothing from the
manager beyond lifecycle and I/O. Debate's structured dialogue is built *on top
of* the same manager, in debate's own per-app coordination layer.

## How to proceed

1. **Build casebook standalone**, scoped exactly as `vision.md` describes.
2. **Encapsulate the likely-shared parts with zero casebook knowledge** as you
   go — backend config/selection, the agent-session manager, and UI components.
   Discipline now, not a published package yet.
3. **Leave coordination policy, layout, and domain model in the app.**
4. **When the debate tool comes, depend on the same encapsulated parts** and ship
   it as a separate installable. Promote the shared code into a real package only
   from the duplication actually hit then — not before.
5. **A unified launcher, if ever, comes last and stays thin.** No plugin host
   until a third tool plus a shared-runtime-chrome need is demonstrated.

## The connection layer: depend on the official ACP SDK

The seam at the bottom of the agent-session manager is **ACP — the Agent Client
Protocol** (Zed's editor↔agent standard at `agentclientprotocol.com`), which
already models exactly what we need: a client connecting to any agent backend
over JSON-RPC/stdio, with first-class sessions, filesystem access, permission
prompts, and streaming updates. Broad agent adoption (Claude Code via Zed's
adapter, Gemini CLI, Codex, Goose, ~30 others) means vendor-agnosticism is a
property of the ecosystem, not something we glue together ourselves.

**Decision: depend on the official Python SDK (`agentclientprotocol/python-sdk`)
for the connection layer rather than hand-rolling JSON-RPC.** It supports building
clients (async base classes, stdio plumbing, lifecycle helpers), is officially
maintained (moved under the org Nov 2025), and the moving landscape is precisely
why leaning on a well-maintained library beats reimplementing against the same
churning spec.

Constraints when depending on it:

- **Pin the version.** The SDK is pre-1.0 (~0.10.x as of mid-2026) and the spec
  churns; expect breaking changes.
- **Isolate it behind our own thin interface** inside the session-manager module.
  SDK churn or a future swap stays contained to one module, never sprinkled
  through the app. This is the encapsulation discipline above, applied to the
  external dependency.
- **Mind the naming trap.** We want the Agent *Client* Protocol
  (`agentclientprotocol` org), **not** the unrelated Agent *Communication*
  Protocol (`i-am-bee`/BeeAI, agent↔agent).
- **Mind the SDK version skew.** TypeScript leads (~0.28.x) while Python lags
  (~0.10.x); a brand-new capability may land in TS first.

## Deferred / open questions

- **Browser UI specifics** — framework, transport between the app process and the
  browser, how the session manager's state reaches the components.
- **Where the shared library physically lives** — same repo (monorepo) vs. its
  own — to be decided when the second tool forces the question, not before.
