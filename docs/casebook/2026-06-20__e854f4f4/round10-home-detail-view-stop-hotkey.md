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

`cancel_turn` (the `s` hotkey) already existed; the user just hadn't noticed it.
It stops **only the focused session's** turn (mirrors the pane's Stop button) —
deliberately never reaching for other sessions.

(A brief experiment to make it stop any running session was reverted at the
user's request — stopping should be a precise, non-destructive action on the
session you're looking at.)

## 3. Dropped the resume_session hotkey

`resume_session` (`e`) was removed as redundant: a focused **closed** session is
opened/resumed by `open_focused` (Enter) or a click — which both reveals it and
resumes it. One fewer binding to remember.
