# Overview

What FalconFox tells a session about itself grew by accretion and is now in
three places, delivered two ways, with no rule about which is which. This case
settles a structure: **orientation is composed from named pieces, all of it
delivered through the prompt channel, and each client owns the text that
describes it.**

Opened in discussion, 2026-09-09. Nothing below is built.

## Where it stands today

Three texts exist, and a session gets at most two of them.

1. **`SESSION_CONTEXT`** (`src/falconfox/config.py`). Six terse bullets.
   Queued into `_pending_context` at spawn and prepended to the **first**
   prompt the session ever receives, split by `=== the user's message follows
   ===`. Never repeated, invisible to the user. Reaches *every* session.
2. **Manager orientation** (`_prepare_manager_workspace` in
   `src/falconfox_telegram/bot.py`). Written into both `AGENTS.md` and
   `CLAUDE.md` in the manager's working directory, and read by the agent's own
   runtime. Reaches the General topic's session only.
3. **Concierge orientation** (`_prepare_concierge_workspace`, same file, same
   mechanism). Reaches the private chat session only.

A fourth path exists but is not orientation: `_context_prompt` in
`coordinator.py` *replaces* the pending context with the prior transcript when
a session resumes on a backend with no native session loading.

**A work session therefore receives `SESSION_CONTEXT` and nothing else.**
That is the entire surface for teaching it anything.

## The problem, concretely

Tags are the worked example. `falconfox tag` is explained at length in the
*manager* orientation — the replace-not-append trap, and why tag order decides
which topic icon is drawn. `SESSION_CONTEXT` does not mention tags at all. So
a work session does not know that its topic icon comes from its own tags, that
`/tags` works in its topic, or that it can tag itself. The session best placed
to keep its own label current is the one told nothing about labels.

The same hole would swallow the attachment tray, which is the work that
triggered this case: it is work sessions that receive files, and work sessions
read `SESSION_CONTEXT` only.

Second problem, in the manager text: it says "forum" and "topic" without ever
defining them, because the definitions belong to a client and there was
nowhere to put them.

## The design

### Four pieces

1. **Session** (global). What a FalconFox session is: a daemon speaking ACP,
   not a terminal, many sessions at once, turns, `falconfox attach`.
2. **Client** (one per client). What that client's surface is and what follows
   from it: for Telegram, forums, topics, tap-to-copy, the constrained
   typing that makes copyable ids matter, and the commands it offers.
3. **Manager** (role). Owning the session lifecycle.
4. **Concierge** (role). Getting the user set up.

### One delivery channel

All of it goes through the prompt channel that landed in `8b9c6fb` ("tell a
session what it is running inside", 2026-09-04). **The `AGENTS.md` /
`CLAUDE.md` workspace mechanism is removed.**

Writing both filenames only ever existed because FalconFox cannot know which
runtime will read them. A prompt needs no such guess, so this is *more*
portable, not less. It also collapses two mechanisms into one and treats work
sessions and infrastructure sessions the same way.

### The daemon composes, not the client

A session may be started in one client and resumed from another, so **every**
client's orientation must always be present. A client cannot know that at
spawn time, so the daemon holds all of them and composes.

This reverses an earlier suggestion in the discussion that each client pass
its own text at spawn. The multi-client argument defeats it.

### Roles are named at spawn

The daemon cannot tell that a session is the manager. Spawn grows a role, and
it **persists in `meta.toml`**, or a resume and a `/clear` will not recompose
the same orientation.

Leaning toward one `--role manager|concierge` over separate `--manager` and
`--concierge` flags: the set is closed, the values are mutually exclusive by
construction, and a third role costs nothing.

### The manager text becomes client-agnostic

It should describe what is constant — the daemon, the CLI, the lifecycle — and
*refer* to the client for the rest. Not "use `/id`", but closer to "every
session knows its own id from the environment, but the client usually has a
cheaper way to hand you one". The client orientation carries the specifics,
and the manager is a session too, so it receives both and the reference
resolves.

### The concierge text stays as it is

It mixes daemon and Telegram detail deliberately and that duplication is
correct: it is the channel that has to work *before* a forum exists. It is the
most special session in the deployment — more so than the manager, which is
better understood as a default session that happens to be used often.

## Tradeoffs accepted

**Orientation changes do not reach existing sessions.** Accepted, and not
globally solvable. `/clear` exists precisely so a new session can pick up new
orientation, including for infrastructure sessions.

**A prompt prefix cannot be re-read after compaction; a file could.** Accepted.
It bites the manager most, whose job description is long and consulted
repeatedly. A future command that simply re-sends orientation would answer it.
Not a present concern: sessions are rotated frequently enough that compaction
has not yet caused trouble.

**Token cost.** Judged negligible, so orientation may be thorough as well as
concise. Where something is better explained by running a CLI command, it
*may* be left to the CLI, but that is an option rather than a rule.

## Open: how clients supply their orientation

Settled that the daemon composes. **Not** settled how the text gets there.

- **Hardcode it daemon-side.** Simple. Costs: `falconfox/config.py` ends up
  carrying forum-and-topic vocabulary, and the text sits far from the code it
  describes, so `/tray` and its explanation drift apart.
- **Clients register at connect.** The Telegram bot already holds a websocket
  to the daemon; it sends its orientation (and its role texts) on connect, the
  daemon **persists** it, and composition draws on every persisted
  registration. Persistence is what makes it survive an offline client, which
  the multi-client requirement demands.

  Worth noting this is close to what the code already does: the manager and
  concierge texts *already* live in `bot.py`, next to the commands they
  describe. Registration keeps them there and gives the daemon a way to
  receive them, instead of the client writing files.

  Costs: a new protocol action, persisted state, staleness until a client
  reconnects, and a bootstrap gap where a session spawned before any client
  ever registered gets only the global piece.

## Related work

- **`ed379c4`** wishlists using more than one prompt content block. Orientation
  composes by concatenation into a single `text_block` today. Real blocks would
  change how it is packed, not what is said, so this case is not blocked on it.
- **`_context_prompt` replaces pending context on resume.** That trade gets
  worse as orientation carries more, and should be revisited here.
- The **attachment tray** work is paused pending this case, and will need a
  client-orientation section of its own.
