# Casebook

This directory is a **casebook** — a collection of cases, each representing a
bounded unit of work (investigation, brainstorm, feature, design, etc.).

## Structure

```
docs/casebook/
  agents.md          # this file
  YYYY-MM-DD__hex/   # case directory
    case.toml        # case metadata
    overview.md      # evolving summary of the case (keep updated)
    ...              # any other files: reports, designs, ADRs, transcripts, etc.
```

## Working with cases

- New cases are created by the user via `casebook new` — agents should
  work within existing cases rather than creating new ones.
- `case.toml` is the `casebook` CLI's interface to the case — a fixed schema the
  tool parses for listing and discovery (`title`, `status`, `keywords`,
  `created`). It is owned by the tool: keep its fields current as the work
  evolves, but don't use it to record the case's content.
- `title` is the primary way cases are discovered, so it should capture the full
  scope of the case — anyone looking for this case's information should be able
  to find it by title. New cases default to "Unnamed case"; rename early and
  refine as the scope becomes clearer.
- `status` is typically `open` or `closed`, though others such as `blocked` or
  `paused` are fine too. Keep `keywords` updated to help future sessions find
  relevant cases.
- Beyond `case.toml`, list the case directory to see what files are available
  and read whichever are relevant to your task. These files hold the case's
  actual content — analysis, reports, decisions, designs, transcripts, etc.
  Code typically belongs in the source tree, not in the case directory.
- Use highly descriptive filenames so that an agent can understand what a file
  contains by reading its name alone. Prefer names like
  `websocket-reconnection-backoff-strategy.md` or
  `user-dashboard-layout-accessibility-review.md` over vague names like
  `report.md` or `notes.md`.
- A case typically grows an `overview.md` as a living summary. Create and update
  it as the case evolves to keep it useful for future sessions.
- Some cases include an `intro.md` with the user's original writeup. When
  present it is the original context, kept for posterity — do not modify it.
- The casebook includes past cases that may provide historical context for
  design decisions, prior investigations, or previously considered approaches.
  Use `casebook list` to browse cases and `casebook show <id>` for details.
