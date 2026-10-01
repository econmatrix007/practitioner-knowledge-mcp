---
description: Carry out one upgrade ticket on a branch, test it, and stop for approval
argument-hint: "[ticket, e.g. mcp-2.3.0]"
disable-model-invocation: true
---

You are carrying out one upgrade ticket from the weekly checkup, under the
user's supervision. Safety comes before speed. Follow these steps in order and
stop where the steps say to stop.

## Never, without the user's explicit "yes" in this conversation

- Merge the upgrade branch, push anything, or delete a branch.
- Restart the always-on service (`launchctl`).
- Close a ticket.
- Touch the database other than through `scripts/backup_db.sh`.

Never run this command headless. If you are running without a person to answer,
stop now.

## 0. Check the starting point

Run `git status --porcelain` and `git branch --show-current`. If there are
uncommitted changes, or the current branch is not `main`, explain and stop.

## 1. Choose the ticket

Tickets are `~/.knowledge-mcp/maintenance/ticket-*.md`. A ticket is open when it
contains `**Status:** open`.

- If `$ARGUMENTS` names a ticket (for example `mcp-2.3.0`), use that one.
- If exactly one ticket is open, confirm it with the user.
- If more than one is open, list them with their proposed dates and flags, and
  ask which to run. **SECURITY** tickets come first.
- If the proposed date is in the future, say so and ask whether to go ahead early.

## 2. Plan first when the ticket says PLAN REQUIRED

If the ticket is flagged **PLAN REQUIRED** (a major upgrade, or moving a private
server onto this package's plugin layer):

1. Read the upstream changelog linked in the ticket.
2. Search this codebase for every API the changelog says changed or was removed.
3. Write a plan to `~/.knowledge-mcp/maintenance/plan-<package>-<version>.md`:
   breaking changes that touch this code, file by file; the order of changes;
   how each will be tested; and how to roll back.
4. Show the user a summary and **stop**. Do not change any code until the user
   reads the plan and says it is approved. Then continue at step 3 below.

## 3. Back up

Run `scripts/backup_db.sh`. Continue only if the output says `integrity ok`.
If it fails, show the error and stop.

## 4. Branch

`git checkout -b upgrade/<package>-<version>`

## 5. Read the changelog

Read the changelog linked in the ticket. List the breaking changes and
deprecations, and for each one say whether this codebase uses the affected
feature (search the code to check). Keep the list for the report.

## 6. Make the change

- **mcp or pyyaml:** if the constraint in `pyproject.toml` excludes the target
  version, widen it. Then `uv lock --upgrade-package <package>==<version>`.
- **Another package (usually a SECURITY ticket):**
  `uv lock --upgrade-package <package>==<version>`.
- **Python:** change `PYTHON_VERSION` in the `Makefile`, `requires-python` and the
  ruff `target-version` in `pyproject.toml` if the minimum changes.
- **This project:** `git fetch --tags`, then `git merge v<version>` into the branch.

Then run `make install`.

## 7. Test

1. `make check`. Every check must pass.
2. `make smoke`. It starts the server the way Claude Desktop does and calls every
   read-only tool. All lines must say PASS.
3. If the changelog mentions the HTTP transport, also start `make run-http` in the
   background and confirm `curl -s http://127.0.0.1:8765/healthz` returns
   `{"status":"ok"}`, then stop it.

## 8. Report and stop

Commit on the branch with a message such as
`build(deps): upgrade <package> to <version>`. Then report:

- what changed (`git diff --stat main`)
- the breaking changes from step 5 and how each was handled
- the results of every check in step 7

Then **stop** and ask three separate questions, waiting for a "yes" to each:

1. Merge into `main`? If yes: `git checkout main`, `git merge --no-ff upgrade/<package>-<version>`, `make install`.
2. Restart the always-on service, if it is installed? If yes:
   `launchctl kickstart -k gui/$(id -u)/com.example.knowledge-mcp`, then confirm
   the health check answers.
3. Close the ticket? If yes: change `**Status:** open` to
   `**Status:** closed <today's date>` in the ticket.

## If anything fails

1. Restore the previous pins: `git checkout main -- pyproject.toml uv.lock Makefile`,
   then `make install`.
2. Commit what you tried on the upgrade branch as `wip: failed attempt`, and keep
   the branch for inspection. Then `git checkout main`.
3. Under `## Findings` in the ticket, record what failed and the exact error.
4. Propose a new date one week out: the first migration day (from
   `~/.knowledge-mcp/maintenance.toml`, default Saturday) at least 7 days from
   today. Update the ticket's proposed date and tell the user.
5. Restore the database from the step 3 backup only if the user asks, following
   `docs/07-backup-and-single-source-of-truth.md`.
