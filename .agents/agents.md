# AGENTS.md

## Branches

`dev` is the development branch: everything lands there first, including
documentation and one-line fixes. `master` is the stable branch, and it lags
behind `dev` at a commit that has been proven in use.

The invariant is that **`master` never diverges from `dev`**: it is always a
direct ancestor of it. That means nothing is ever committed to `master`
directly, and `master` moves only by fast-forward to a commit that is already
on `dev`. Branch new work off `dev`, and merge it back into `dev`.

Ignoring this is cheap to do and expensive to find: the divergence surfaces
much later as a merge conflict at deploy time. See the "Branches" section of
[deploy/README.md](../deploy/README.md) for how the release step uses this.

## The web UI is not a client

`src/falconfox/web/static/` is a **dead** browser UI: it was written against
the old case- and project-centric session model, flattening that model broke
its navigation, and it has been unmaintained since. It is not a client, it is
not a second front-end to keep in step, and it is not a description of how the
system works. Do not read it to learn the shape of anything, do not wire new
work to it, and do not repair it in passing. Telegram is the only client.

Do not confuse it with `src/falconfox/web/server.py`, which is very much
alive: that module *is* the daemon's HTTP and websocket API, the thing every
client and the CLI actually talk to. It only happens to also mount the dead
static assets.

The assets are slated for deletion soon, with a repair possible after that.
See the entry in [docs/wishlist.md](../docs/wishlist.md).

## Checkouts

`~/projects/falconfox` is the development checkout, and it is on `dev`. It is
where you are, and it is what the dev instance runs. Work in a worktree under
`.worktrees/`, branched from `dev`, and merge back into `dev`.

`~/projects/falconfox-stable` is the stable checkout, on `master`, and is the
only thing a deployment runs. It is the fallback, not the daily driver: dev is
where the work happens, and stable is kept proven so there is something to fall
back to. Do not develop in it and do not commit there: it moves by
fast-forward alone.

Both checkouts must stay clean, so never edit either one in place.

One operational warning: restarting the daemon kills every agent session it
is running, including your own turn, whether you restart it with `update.sh`
or by hand. Detach the restart and end your turn.

`update.sh` is for the **stable instance only**, despite its name reading
generally. It
fetches from `origin` and restarts `falconfox-daemon` and
`falconfox-telegram`, so it cannot restart the dev instance, which runs
unpushed local `dev` from this checkout under `falconfox-dev-daemon` and
`falconfox-dev-telegram`. Restart those by hand and detached:

```
systemd-run --user --collect --unit "falconfox-dev-restart-$(date +%s)" \
    --on-active=15 systemctl --user restart \
    falconfox-dev-daemon.service falconfox-dev-telegram.service
```

For stable, `update.sh --detach-restart` does the same thing for you.
