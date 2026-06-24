# Multi-Project Support

## What changed

The app is no longer tied to a single project directory. `casebook serve` starts
a project-agnostic server; projects are selected through the UI.

### New routing

```
/                                      project browser (new home)
/project/{project_id}/                 case browser (was /)
/project/{project_id}/case/{case_id}   case view (was /case/{id})
/project/{project_id}/scratch          scratch (was /scratch)
```

`project_id` is a 12-char hex hash of the resolved absolute path.

### Project path cache

Previously-opened projects are cached at
`~/.config/casebook/projects.json`. Entries are pruned automatically when their
path no longer contains a valid casebook. No explicit registry -- opening a
project adds it to the cache; moving the directory just causes the old entry to
be pruned next time.

### Initialization

The project browser lets users paste a directory path and open it. If the
directory has no `docs/casebook/`, a prompt offers to initialize one (creates
`docs/casebook/` and `.casebook/`).

### CLI

Stripped to `casebook [--host] [--port]` only. All other subcommands (init, new,
list, show, hide, delete, refer) removed -- their functionality is available
through the UI.

### Backend changes

- `CaseCoordinator` is unchanged -- still scoped to a single project root.
- The server holds a `dict[project_id, CaseCoordinator]`, lazily instantiated.
- All REST and WebSocket endpoints are project-scoped under
  `/api/projects/{project_id}/` and `/ws/{project_id}`.

## Files modified

- **New**: `src/casebook/projects.py` -- path cache CRUD
- `src/casebook/cli.py` -- stripped to serve-only
- `src/casebook/web/server.py` -- multi-coordinator, new routes
- `src/casebook/web/static/app.js` -- new routing, project browser UI
- `src/casebook/web/static/index.html` -- project browser sections
- `src/casebook/web/static/style.css` -- project list styling
