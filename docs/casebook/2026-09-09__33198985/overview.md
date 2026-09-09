# Overview

The bot can send files and cannot receive them. This case builds the inbound
half, and it is **two things rather than one**: the daemon gives every session
a **file store** bound to that session's lifetime, and the Telegram client
builds a **tray** on top of it, because a chat has no compose step and has to
synthesise one.

Separating those two is the whole result, and the line between them is
ownership of a lifetime against ownership of a user interface.

Designed in discussion 2026-09-08/09, paused behind the orientation case
([2026-09-09__1071993a](../2026-09-09__1071993a/overview.md)) because a session
only learns any of this through orientation. That case has landed. Nothing
below is built.

## Where it stands today

`_handle_update` in `src/falconfox_telegram/bot.py` reads `message["text"]`,
and a message without one is answered with "Text messages only in this PoC."
once the topic service messages are filtered out. That is the whole of it.

The **outbound** direction is built and is worth reading first, because it
settles the assumption both directions rest on. `coordinator.attach` resolves
a path, emits an `attachment` event, and waits for the client to report back
through `resolve_attachment`; `_deliver_attachment` uploads it and answers.
The client and the daemon share a filesystem, so a path is a sufficient
handoff and bytes never cross the socket. Inbound works the same way in
reverse.

Two things do not exist. The Telegram API client has no `getFile` and no
download, and a session's state directory holds `meta.toml` and
`transcript.jsonl` and nothing else.

## The tray is a workaround for a missing compose step

This is the reframing the design turns on, and it was not obvious. It is easy
to read the tray as the feature and storage as its implementation detail. It
is the other way round.

Telegram has no compose step. Files arrive as separate committed messages,
with no send event tying them to the text that is about them, and an **album**
arrives as *n* messages with no album-complete signal. There is nothing to
attach a file *to*. The tray is the composer Telegram does not have, built out
of held state and a receipt.

That makes it a fact about a chat interface rather than about FalconFox, and
it belongs to the thing that has the problem. Anything with a compose step,
down to a plain `falconfox send --attach`, needs none of it.

**The daemon's half is the lifetime.** A file has to live somewhere, and the
only lifetime that fits is the session's, which is the daemon's to own. Both
alternatives fail on exactly that. A client writing into the session's state
directory makes two writers of one directory, so `falconfox delete` removes
files the client still lists and the client finds out when the user taps an id
that no longer resolves. A client keeping a directory of its own has to
reimplement session deletion by watching `session_deleted`, and leaks every
file of every session deleted while it was not running.

None of this is an argument from other clients. There is one client. If a
second ever arrives it inherits the store, but that follows from putting the
lifetime where the lifetime is rather than being the reason for it.

## A file does not prompt the agent by itself

Within Telegram, this is the decision the rest follows from.

A file lands in the tray and waits. The next real message sweeps whatever is
in the tray and carries it, so one message can be about five photos.

The alternative was rejected on the album. If each file were its own prompt,
sending three photos and asking one question about all of them is impossible,
and an album, arriving as *n* messages with nothing marking the last, would
need a debounce timer to guess when the set had finished. The guess would be
wrong exactly when the network is slow. The tray deletes that problem rather
than solving it.

The cost is that the most natural gesture on a phone, a photo with the
question typed into its caption, does **not** start a turn. Making a caption
prompt would put the album race straight back, because Telegram carries an
album's caption on one of its messages, so the captioned photo would fire a
turn while the rest of the set was still arriving.

It is a surprise that has to be paid for rather than argued away, and the
receipt is what pays for it: every file gets one, and it says when the file
goes out.

A command such as `/list` leaves the tray alone. Only a real prompt sweeps it.

## The daemon: a file store per session

```
<state>/sessions/<session_id>/inbox/<file_id>/<name>
```

Three calls, and no fourth. **Add** copies a file in under a name and returns
its id and its stored path. **Remove** deletes one by id. **Clear** deletes
all of a session's files.

**The directory is the entire state.** The id is the directory name, the name
is the filename, the arrival time is the mtime. There is no record file
because there is nothing left to record: everything else about an attachment,
its caption most of all, belongs to whichever client received it.

A **directory per file** rather than an id for a filename, so collisions are
impossible while the real name survives intact. A name carries information:
`prod-error.log` says something that `a1b2c3d4.log` does not, and renaming
would have to guess at extensions like `.tar.gz`.

**The daemon generates the id**, 8 characters, matching session ids. That is
what makes it collision-free across clients, and it means there is one id in
the system rather than a client id and a storage id that have to be kept in
step. It is also the safer key for `remove`: an id cannot address anything
outside the session's own directory, where a path could and would have to be
validated against traversal.

**Add copies, it does not move.** Outbound `attach` does not consume the file
it is given, and `falconfox give` would hand over a file the caller still
wants. A client that downloaded to a temporary file deletes its own. At a
20MB ceiling the copy costs nothing worth reasoning about.

**Lifetime is the point.** The store is inside the session directory, so
`delete_session` already removes it and no client has to watch for that. A
client keeping its own directory instead would have to wire `session_deleted`
itself, get it right, and still leak whenever it was not running at the
moment a session was deleted.

**An ephemeral session has no store.** Ephemeral means nothing on disk, and no
session a user talks to is ephemeral.

### Remove and clear

**Remove is the tray's discard.** A file dropped by `/tray` is never going to
reach the agent, so nothing is left to keep and the bytes go at once. That is
the entire justification, and it wants no policy on top of it.

**Clear takes a whole session's files in one call**, the bulk form of the same
thing, for a store that has grown while its session is still wanted. Nothing
calls it on a schedule. What might eventually, by age or by size, is a policy
nobody has proposed, and this case does not invent one: the stored paths are
quoted into the session's transcript, so any sweep is deleting references an
agent still holds, and that deserves its own decision rather than a default.

### What was tried first

Three shapes preceded this one and each failed differently. They are recorded
because the third is the interesting one.

1. **The client writes the bytes itself**, into the session's state directory.
   Reads as the smaller change, since every mechanic below is Telegram's. It
   is two writers to one directory, and the failure is ordinary rather than
   exotic: `falconfox delete` removes files the bot still lists, and the bot
   finds out when the user taps an id that no longer resolves.
2. **The daemon sweeps the tray into the prompt.** It already composes prompt
   parts at `send`, for orientation and for the resumed transcript, so a third
   producer there looks natural. But the client is what turns a chat into a
   prompt: it joins queued messages into one and decides what the agent is
   shown. A daemon injecting content into a prompt the client authored makes
   the client's own message something it cannot see the whole of.
3. **The daemon stores a `pending` flag it never acts on.** This was written
   down and then reversed, and it is the useful failure: the daemon would have
   owned the vocabulary of a mechanism it did not own. A word whose meaning
   lives entirely in one client should live there too. Chasing that smell is
   what produced the split above, and the flag disappears once the tray is
   understood as a composer rather than as storage.

## Telegram: the tray

The tray is a list of ids per session, held in the bot's own state beside
`topics.json` and the in-flight turn record, which is the third user of a
pattern that already exists rather than new machinery. Each entry is a storage
id, its path, and the caption the file arrived with.

A session delete drops its tray entry in the same handler that already deletes
the topic, so the two go together and there is no window where one outlives
the other.

**A lost tray file is a recoverable state**, not a corrupt one: the files are
still in the store and nothing is pending, which is the same as a tray that
was swept. That is the failure mode worth having.

### The prompt

`_forward` composes, appending one line per file in arrival order, each with
its own caption on its own line rather than merged into the message:

```
attached: /home/…/sessions/<sid>/inbox/4f2a91c8/photo.jpg
attached: /home/…/sessions/<sid>/inbox/7b1d0e35/prod-error.log (the error I mentioned)
```

Sweeping clears the tray and deletes nothing. The agent is given a path and
may read it during the turn or ten turns later.

A path, not the bytes. That is today's single text block rather than a
preference, and it is a mild limitation: an agent that can read a file loses
little. It also means **this case does not close the content-blocks work**.
The wishlist entry names these lines as a producer still gluing text together
and that stays true, but with the client composing, the fix arrives when the
`send` action grows an array a client can fill, not when the daemon learns
about images.

Composing in `_forward` also handles the mid-turn case for free, since a
queued message flushes through `_forward` like any other prompt. The sweep
happens at the one moment the prompt actually goes out.

## `/tray`

Shaped after `/tags` and living in the **Session** section of `/help`:

- no arguments shows the tray, with each id as tap-to-copy text
- `-` clears it, deleting the files
- one or more ids removes those

The shape is borrowed from `/tags` and the meaning is **inverted**: `/tags`
arguments replace the set, `/tray` arguments remove from it. Removal fits the
common case, which is dropping one bad photo out of five, so the help line has
to say "remove" plainly rather than leaving it to be inferred from the other
command.

`-` deletes the bytes with no grace period. Recovering a mistaken clear was
considered and rejected as complexity a deliberate `-` does not warrant. Note
it clears the *tray*, not the store: files already carried into a prompt are
not what the user is looking at when they type it.

`/tray` in a chat with no session answers like `/tags` does.

**Reactions were considered and dropped** as the removal mechanism. An earlier
shape had the user react to a file to unattach it. `/tray` covers it without
needing `message_reaction` in `allowed_updates`, and without the private chat
gap: reaction updates require the bot to be an administrator, which holds in
the forum (verified) and means nothing in a private chat.

## Receipts and reactions

Every file gets a **receipt**: a message carrying its id in a `<code>` span so
it can be tapped and copied, and saying that the file goes out with the next
message. Both halves earn their place. The id is what `/tray` removal needs,
and the sentence is what stops the design's one surprise from reading as the
bot ignoring a photo.

The file's own message also gets 👀, the marker a queued message already
wears. The receipt says what happened once; the reaction says what is still
true, which is what makes the later change of state visible without spending
another message on it. Cleared on sweep, exactly as `_flush_queue` clears the
markers of the messages it joined, and 💔 when the item is removed by `/tray`,
matching `/unqueue`.

A file arriving mid-turn gets the same receipt and the same 👀. It is held
either way, so there is nothing to special-case.

**Receipt noise is a real risk and is left to use.** An album of five is five
receipts on a phone screen. Two ways out were floated: a setting to trim the
wording around the id, and one to suppress receipts entirely and have a bare
`/tray` reply to each file retroactively with its id. Neither is built. The
first is not worth guessing at before the thing has been used once, and both
need somewhere to live that does not exist, since Telegram's configuration is
environment variables today and a file for it is its own small case.

## What arrives, and what is stored

Accepted: photos, documents, video, audio, animations, video notes, and
**voice messages**, stored as the file they are. Voice *input* remains
deferred and is untouched by this: nothing here transcribes anything, and an
`.oga` in the tray is strictly better than "Text messages only".

Refused, with the reason said: stickers, and anything over the download limit.

**Names are taken, never invented.** Documents, video and audio usually carry
`file_name`, used as it stands once reduced to a basename and stripped of
anything that cannot be a filename. A photo carries no name at all, so it is
stored as `photo.jpg`, with the extension from the `file_path` that `getFile`
returns and nothing else read into it. `voice.oga` and the rest follow the
same rule. Making up `IMG_20260909_142530.jpg` would be inventing provenance
the API did not give us.

**The 20MB cap is the Bot API's, not a policy.** `getFile` will not serve a
file larger than that, against 50MB for upload, an asymmetry of the API. The
size is read off the message before any download is attempted, so the refusal
is immediate and names the real reason rather than surfacing whatever
`getFile` fails with.

## Tradeoffs accepted

**A swept file is not deleted**, so a session's store grows without bound and
only a delete reclaims it. Accepted: a 20MB ceiling on things a human sent by
hand is not a disk problem, and `clear` is there for the case that proves
otherwise.

**Nothing tells the agent a file arrived until the user sends a message.** The
tray is the whole point, so this is the design working. Worth stating because
a session asked "did you get my photo" mid-wait has to be able to answer no
correctly, which is orientation's job.

## Orientation and help owe

The photo re-encoding note is **already written**: the orientation case landed
a paragraph in the Telegram client piece saying that Telegram re-encodes
photos and that resending as a file gets the original.

What is owed is the tray itself, in the Telegram client orientation: that
files land in a tray and wait, that a message sweeps it, and that the paths
arrive in the prompt. **Not the global piece**, which was the plan and is
wrong: the store is reachable only through a client, so a session with no
client would be told about files it can never be given. What an agent actually
needs to know about the store is that a path it was handed stays valid, and
that belongs beside the tray text. `/tray` also joins
`COMMANDS`, `COMMANDS_HELP` and the `/help` Session section, and the test that
every command in `COMMANDS` appears in the help text is what guards it.

## Implementation plan

In dependency order. Steps 1 and 2 are independent of each other.

1. **The store.** `sessions/<id>/inbox/`, with add, remove and clear on the
   coordinator and over the API, refusing an ephemeral session.
2. **Download.** `getFile` and a download on the Telegram API client, the size
   pre-check, and the name rules.
3. **Receiving.** `_handle_update` routes a non-text message to the store
   instead of refusing it, records the tray entry, and sends the receipt and
   the reaction.
4. **The sweep.** `_forward` prepends the `attached:` lines and empties the
   tray. Reached by the queue flush for free.
5. **`/tray`.** Show, clear, remove by id, and the markers each leaves on the
   file's message.
6. **Orientation, help and `/help`**, per the section above.
7. **Tests and the README.**

## Related work

- **The outbound half** (`coordinator.attach`, `_deliver_attachment`) is the
  mirror of this and settled the co-location assumption it rests on.
- **Typed prompt content blocks**, in [wishlist.md](../../wishlist.md).
  Narrowed by this case rather than closed, as described above.
- **The orientation case**
  ([2026-09-09__1071993a](../2026-09-09__1071993a/overview.md)) is what this
  waited for, and is the reason the tray can be explained to a session at all.
