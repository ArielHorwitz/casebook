# Round-11 feedback: caseless scratch sessions, logo, config naming

## 1. Caseless ("scratch") sessions, promotable into a case

Standalone sessions with **no case directive/preamble** and **no files panel**,
for one-off queries:

- A dedicated **`/scratch` page** (linked from the home page; hotkey `scratch`,
  default `S`), styled like a case page but without files.
- Implemented on a reserved `scratch` case id: `add_agent`/`resume_agent` skip
  case resolution, the directive, and file watching; sessions persist under
  `.casebook/sessions/scratch/`.
- **Promotion** (`↑ case` button → `POST /api/promote`): creates a new case, moves
  the session's on-disk data into it, and **re-tags the live session in place**
  (the subprocess keeps running), then the browser navigates to the new case
  page. Engine sessions gained `retag()`; storage gained `relocate()`.

Verified end-to-end against echo: a scratch reply carries no casebook directive,
the session persists under `scratch/`, and after promotion it lives in the new
case and stays responsive.

## 2. Logo in the top bar

`.mydev/logo.png` is copied into `web/static/logo.png` and shown as the brand in
the top bar on **every** page (home, case, scratch), replacing the text wordmark.

## 3. Clearer config key

The backend default key is now **`default_backend`** (the old `default` is still
accepted for back-compat). Docs and the README example updated.

## New hotkeys this round

- `scratch` (`S`) — open the scratch page (works anywhere).
- `home` (`h`) now works anywhere (not just case pages).
