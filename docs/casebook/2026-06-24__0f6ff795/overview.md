# LimitOverrunError on large JSON-RPC messages

## Problem

The receive loop in `acp.Connection._receive_loop` crashes with:

```
asyncio.exceptions.LimitOverrunError: Separator is found, but chunk is longer than limit
```

This happens because `asyncio.StreamReader` defaults to a 64 KiB buffer limit.
When an agent sends a JSON-RPC line larger than 64 KiB (e.g. a tool result
containing a large file), `readline()` raises `LimitOverrunError`.

## Root cause

`spawn_agent_process` → `spawn_stdio_transport` → `create_subprocess_exec` was
called without a `limit` argument, inheriting the 64 KiB default.

## Fix

Pass `transport_kwargs={"limit": 100 * 1024 * 1024}` (100 MiB) to both call
sites:

- `src/casebook/engine/session.py` — interactive sessions
- `src/casebook/engine/oneshot.py` — one-shot prompts

The `acp` library already plumbs `transport_kwargs` through to
`create_subprocess_exec`, so no upstream changes were needed.

## Why 100 MiB

The failure mode is asymmetric: too low crashes the session and loses work (this
already happened); too high lets a buggy subprocess exhaust memory before
backpressure kicks in. 100 MiB is well beyond any realistic single JSON-RPC
message (which carries one tool result or prompt) while still capping a
pathological subprocess before it can OOM the host. If agents ever produce
single lines approaching this size, the protocol itself (line-delimited JSON
over stdio) would need rethinking.
