# Round-4 feedback: session bootstrap and UI polish

A fourth batch of smaller fixes.

## 1. Resume notice wording

Dropped the trailing "so the agent receives the prior conversation with your next
message" from the imperfect-resume notice.

## 2. Cluttered session header wrapped the label across three lines

The pane header is now two rows: the `Session N · backend` label on its own line
(single line, ellipsized if long), and the idle/working indicator plus all the
controls (model picker, always-allow, rename, name, resume, close, delete) on a
second wrapping row.

## 3. New session no longer queries the agent on start

Previously casebook sent the directive as the session's first turn, so the agent
replied before the user said anything. Now `start()`/`resume()` only open the ACP
session (idle); the directive is **prepended to the user's first message** by the
coordinator (the same pending-context mechanism as the resume transcript replay).
A brand-new session stays silent until the user speaks, and the directive is no
longer shown as its own bubble. For non-natively-resumed sessions, the directive
is folded in ahead of the replayed transcript.

## 4. File previews: render markdown, and Escape closes the modal

`.md`/`.markdown` previews now render through the shared markdown styles (the same
ones agent bubbles use, refactored into a reusable `.markdown` class). Other files
keep a monospace plain view. Escape closes the file preview (and the shortcuts
overlay).
