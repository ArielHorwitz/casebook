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
3. **Manager** (role, owned by the daemon). Owning the session lifecycle.
   This is a *builtin* session type, not a Telegram one: managing the daemon's
   sessions through an agent is useful to every client, and the orientation
   for it has no client-specific detail in it. Telegram merely has a natural
   place to put it — the always-on General topic.
4. **Concierge** (role, owned by the Telegram client). Getting the user set
   up. This one genuinely is client-specific: it exists because Telegram
   requires a private chat before a forum can be reached at all.

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

### Roles are named at spawn, and they compose

The daemon cannot tell that a session is the manager. Spawn grows roles, and
they **persist in `meta.toml`**, or a resume and a `/clear` will not recompose
the same orientation.

**Roles are a set, not a choice.** An earlier draft had one mutually exclusive
`--role manager|concierge`, which bakes in an assumption the daemon has no
business making: that a client-specific role cannot compose with the manager
role, or with another client's role. Nothing about the manager conflicts with
being something else as well. So a session carries zero or more roles and gets
the orientation for each.

This also fixes where the two roles live. The **manager** is the daemon's own,
so the daemon carries its text. The **concierge** belongs to Telegram, so
Telegram carries it, by the same registration route as the client
orientation.

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

## How clients supply their orientation: a file, not a connection

The daemon composes, and clients hand it their text by **writing it to a
shared runtime directory when they initialise**. The daemon reads what is
there. No protocol action, no connection involved.

The alternative considered was registering over the websocket the Telegram bot
already holds. It was rejected for making orientation depend on process start
order: a session spawned before a client had connected would silently get an
incomplete orientation. That is not a hypothetical about today's single
client so much as the shape of a bug that appears rarely and reads as
inexplicable when it does — and a feature to enable and disable clients, which
is plausible, would make it ordinary. A file removes the ordering question
instead of managing it.

Secondary virtues: it survives a client restart, it survives transient
connection trouble, and it can be read with `cat` when something looks wrong.

**The daemon reads at spawn, from `XDG_RUNTIME_DIR`.** Both halves were argued
the other way first and both were changed by the same fact.

Reading once at daemon startup is simpler and has the appealing property that
the files cannot shift under a long-running process. It does not work here:
`falconfox-telegram` is `After=falconfox-daemon`, correctly, since the bot is
a client that connects *to* the daemon. So the daemon always starts first, and
on a tmpfs that is empty every boot it would read nothing and describe no
client at all until someone restarted it by hand. Pairing startup reads with a
durable directory fixes that but leaves the daemon permanently one restart
behind whatever the client last wrote.

Reading per spawn costs a directory listing and removes both problems.

With per-spawn reads, tmpfs beats a durable directory on **accuracy**: the
orientation then describes the clients that are actually running, so a session
spawned while the bot is down is not told it has a `/tray` and topics. A
durable directory would keep describing a stopped client indefinitely, and
wrong information is worse than missing information here, because an agent
acts on an affordance it is told it has. The tmpfs failure mode is also the
milder one — a spawn in the gap between daemon start and client start, which
self-corrects on the next spawn and is close to unreachable for a
Telegram-originated spawn, since that requires the bot to be up already.

Note a subdirectory *per daemon run* cannot work: clients would have to know
the run id before the daemon creates it. Tmpfs already gives per-boot
granularity, which is the same intent.

The case for this over hardcoding daemon-side is not mainly decoupling. It is
that the manager and concierge texts **already** live in `bot.py`, next to the
commands they describe. Hardcoding client text daemon-side would move them
away from that code, which is a regression from the current state rather than
a neutral choice.

## Related work

- **`ed379c4`** wishlists using more than one prompt content block. Orientation
  composes by concatenation into a single `text_block` today. Real blocks would
  change how it is packed, not what is said, so this case is not blocked on it.
- **`_context_prompt` replaces pending context on resume.** That trade gets
  worse as orientation carries more, and should be revisited here.
- The **attachment tray** work is paused pending this case, and will need a
  client-orientation section of its own. Its design is recorded in
  [wishlist.md](../../wishlist.md).
