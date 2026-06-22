# Round-9 feedback: richer home page, column resize hotkey, top-bar redesign

## 1. Home page: more detail, shared hotkeys, delete cases

- Each case row now shows the session count, created date, keywords, and id, with
  a delete (🗑) button.
- The "new" key is shared: `n` creates a **case** on the home page and a
  **session** on a case page (and `c` still creates a case anywhere).
- Cases can be **deleted** — `d` on the home page deletes the focused case (with
  confirmation), the 🗑 button does the same. Deletion stops and erases the case's
  sessions, removes the directory (`DELETE /api/cases/<id>`), and is announced on
  the bus so open browsers refresh (a case page whose case is deleted returns
  home).

## 2. Dynamic column resize via hotkey

`[ui] session_widths` (default `20/33/50/66/75/100%`) plus a `cycle_width` hotkey
(default `w`) step the session-column width through the list, applied as the
`--session-width` CSS variable and remembered per-browser in localStorage.

## 3. Top-bar redesign

The old bar (logo + indistinct "← Cases" link + faint hint-like title) is
reworked: the home page leads with the casebook brand; a case page leads with a
**button-styled `← Cases`** and a **prominent case title** (proper weight/size/
color). Brand shows only on home, back+title only on a case page.
