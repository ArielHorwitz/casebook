I have some off-the-cuff feedback on the initial implementation (commit `567aedbe27e0`) after playing around with the app for a few minutes. This case is all about triaging, planning, and prioritizing this feedback.

# Feedback

i dont think i'm interested in the original cli commands. we should be able to start new sessions from the ui.

configs should be in `~/.config/casebook/config.toml` or similar.

i want to enable an "always allow" option for permissions. i am used to using "auto mode" in claude code, but i suspect that is actually more intricate than "always allow" (i think it uses another "classifier" model that rejects commands it deems dangerous or otherwise unwelcome).

all sessions should be stored to disk and should be resumable. i would argue that seeing this list of sessions is more important than the list of case files.

i want to be able to name sessions manually (currently just "Agent N") as well as have a button "name session" which will use the model to name the session. the (system) prompt for this query should be configurable - i really dont like how claude code names sessions.

the idea of the `intro.md` should probably be reconsidered and instead we can suggest to the user at the start of a new case to fill in an `intro.md` and possibly other documents. for now, we can just forget the `intro.md`.

the `casebook/agents.md` directive that was placed on-disk in the casebook dir should probably just be inserted into the system instructions. we therefore also don't need a preamble.

rendering the markdown of the model's response is super important.

i don't like the idea of auto-fetching-and-running npx for the backend. backends should be installed explicitly. we can have a builtin "echo" backend in case no other is available.
