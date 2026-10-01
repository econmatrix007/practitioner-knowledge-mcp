# Frequently asked questions

## Does my data leave my Mac?

The database never leaves the machine it lives on, and the server sends
nothing anywhere. But when Claude reads an idea or a framework through a tool,
that text becomes part of your conversation, which goes to Anthropic like
anything else you type into Claude. Your Claude plan's privacy terms apply to
it. If an idea is too sensitive for a Claude conversation, do not ask Claude to
read it.

## Does it work on Windows?

Not officially. The server is plain Python and may run, but the setup scripts,
the always-on service, and the guides are written for macOS. Linux works for
the server and tests; the launchd service is macOS only.

## Can I use it with other AI apps?

Yes, with any app that supports MCP servers over stdio or Streamable HTTP. For
example, Claude Code can add it with `claude mcp add`; see the Claude Code
documentation for the current syntax. The command to run is the same one the
Claude Desktop settings use:

```
uv --directory /Users/you/dev/practitioner-knowledge-mcp run knowledge-mcp --transport stdio
```

## Can I import my existing notes?

Not with a built-in command yet; it is on the roadmap. Today you have two
options:

- Ask Claude to do it in a chat: paste a note and say "store this as an idea in
  practitioner-knowledge." Claude fills in the fields and you approve each one.
- Write a short script or plugin that reads your files and calls the database
  functions in `src/knowledge_mcp/db.py`. See
  [05-add-your-own-tools.md](05-add-your-own-tools.md).

Run `scripts/backup_db.sh` before any bulk import.

## How big can it get?

Each idea's title can be 200 characters, and each text field 20,000 characters
(about eight pages). An idea can carry 20 tags. SQLite handles millions of
rows, so the practical limit is how many ideas you write, not the software.

## Is my data encrypted?

The database is an ordinary file. Turn on FileVault (System Settings, then
Privacy & Security) to encrypt your whole disk; that protects the database if
your Mac is lost or stolen. Remote connections travel inside Tailscale's
encrypted network.

## Can I sync it across my Macs?

Do not sync the live database file through iCloud, Dropbox, or similar
services; it can drift or corrupt. Keep one database on one always-on Mac and
connect the others to it. See
[07-backup-and-single-source-of-truth.md](07-backup-and-single-source-of-truth.md).

## Can I delete an idea?

No tool deletes ideas, by design: a mistaken or injected instruction cannot
wipe your work. Set the status to `archived` instead. Archived ideas stay
searchable, and you can filter them out with `list_ideas`.

## Claude Desktop says the server timed out the first time.

The first launch is slow while uv sets up Python and the project's packages.
Click Retry. Later launches take about a second.

## What does it cost?

The software is free under the Apache 2.0 license. You need a Claude plan that
supports connecting MCP servers in Claude Desktop, and a Tailscale account for
remote access (its personal plan is free at the time of writing).

## Where do I get help?

Read the guide for the step that failed; each one ends with a troubleshooting
table. Then see [SUPPORT.md](../SUPPORT.md). Support is best effort, from a
volunteer, with no guaranteed response time.
