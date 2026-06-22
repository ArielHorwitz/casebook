# Round-10 feedback: home detail view, wider sidebar, stop hotkey

## 1. Home page: compact list + details in the main view

Reworked to match the intended layout:

- The sidebar case list is **compact and title-only**; titles no longer wrap
  (single line, ellipsized).
- **Focusing** a case (click or arrow keys) shows its **details in the main
  view** — title, status, session count, created date, keywords, files, the
  session list, plus *Open case →* and *Delete case*. (A plain click focuses;
  ctrl/middle-click still opens the case in a new browser tab; Enter opens it.)
- The **sidebar is wider** (240px → 320px) so case/session titles read without
  breaks.

## 2. Keyboard stop for a running turn

`cancel_turn` (the `s` hotkey) already existed but only targeted the focused
session. It now stops the focused session if it's working, otherwise **any**
running session — so a long tool call can be aborted from the keyboard even if
focus has moved. (It mirrors the pane's Stop button.)
