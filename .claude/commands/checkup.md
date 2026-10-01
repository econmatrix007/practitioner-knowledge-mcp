---
description: Explain the latest maintenance checkup report in plain language
allowed-tools: Read Glob Grep
---

You are helping a non-developer understand their knowledge server's latest
maintenance checkup. Your job is to read and explain. You do not change anything.

## Rules

- Do not edit, create, move, or delete any file.
- Do not install, upgrade, or uninstall anything. Do not run `uv`, `pip`, `make`,
  `git` commands that change state, or `launchctl`.
- If the user wants to act on a ticket, tell them to run `/migrate`.
- Write for someone who is not a programmer: short sentences, no jargon without
  a one-line explanation.

## Steps

1. Find the newest report: the file named `report-YYYY-MM-DD.md` with the latest
   date in `~/.knowledge-mcp/maintenance/`. If there is none, say so and tell the
   user to run `make checkup` in the project folder, then stop.
2. Read the report. Note its date. If it is more than 8 days old, say the weekly
   checkup may not be running, and suggest
   `deploy/macos/install_launchd.sh status checkup`.
3. Give the overall picture in two or three sentences: is everything healthy,
   and is anything waiting on the user?
4. Explain every yellow and red item: what it means, why it matters, and the one
   thing to do about it. Skip green items unless the user asks.
5. For each proposed upgrade, read its ticket (`ticket-<package>-<version>.md` in
   the same folder) and explain:
   - what would change and how risky it is (patch, minor, or major)
   - the proposed date, and why that date (the soak period after a release)
   - any **SECURITY** flag: this one should not wait
   - any **PLAN REQUIRED** flag: `/migrate` will draft a plan for approval first
   - that `open ~/.knowledge-mcp/maintenance/ticket-<package>-<version>.ics` adds
     the proposed time to their Calendar, after Calendar asks them to confirm
6. Mention tickets whose status is still open from earlier reports.
7. End by asking whether they have questions. Answer them from the report,
   the tickets, and the project's docs in `docs/09-maintenance-and-upgrades.md`.
