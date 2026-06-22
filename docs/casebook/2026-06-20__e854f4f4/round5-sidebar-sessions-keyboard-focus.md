# Round-5 feedback: full keyboard focus flow, and sessions in the sidebar

## 1. Enter focuses the input, Escape leaves it

To stay entirely on the keyboard without typing/hotkey collisions:

- **Enter** (the `open_focused` hotkey) — on the home page opens the focused case;
  on a case page, opens the focused *closed* session or focuses the *open*
  session's composer input box.
- **Escape** — when the composer is focused, blurs it back to keyboard
  navigation (and still closes the file/shortcuts modals when open).

While the composer is focused the global hotkeys don't fire (the handler bails on
`isTyping`), except Escape-to-blur — so prompting and navigation never collide.

## 2. Close/open reworked; sessions live in the sidebar

The old behaviour left a *closed* session as an empty pane with a Resume button —
it still took space, defeating the point of close-vs-delete.

New model:

- A case page's **sidebar lists every session** (the source of truth), with a
  state dot, name, rename, and delete. The main area renders panes **only for
  open (live) sessions**.
- **Close** collapses a session to the sidebar — subprocess stopped, history kept,
  no pane. **Open** (click it in the sidebar, or Enter on a closed focused
  session) resumes it into a pane. **Delete** removes it and its history. This is
  the close-vs-delete distinction the user expected.
- `focus next/prev` cycles **all** sessions (open and closed) in the sidebar.
- The `+ session` button, backend picker, and file list moved into the case
  sidebar; the in-main session bar is gone. The main area shows a hint when no
  sessions are open.

No backend change was needed — the engine already modelled live vs stored
sessions; this is a presentation rework of how they're surfaced.
