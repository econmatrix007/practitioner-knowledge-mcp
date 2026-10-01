# Maintenance and upgrades

Software you rely on needs care: new versions, security fixes, a database that
should stay healthy. This guide sets up a weekly checkup that watches all of it
and tells you what needs doing, without ever changing anything on its own.

## How it is designed

A deterministic script inspects. Claude Code proposes and carries out changes
while you watch. You decide.

| Layer | Runs | Does | Never does |
|---|---|---|---|
| Checkup script | Weekly, by launchd | Inspects, reports, proposes dates, writes tickets | Installs or changes anything except backups |
| `/checkup` in Claude Code | When you open Claude Code | Reads the latest report and explains it in plain language | Modifies code or dependencies |
| `/migrate` in Claude Code | When you choose, on the proposed date or later | Carries out one ticket on a separate branch, tests it, reports | Merges, restarts the service, or touches your data without your "yes" |

The weekly job makes no AI calls. It is free, predictable, and safe to run
while you are away.

The checkup uses the network only for the read-only version checks listed in
[08-security.md](08-security.md#no-telemetry). The project collects no usage data
and sends nothing to the maintainer.

## What the checkup looks at

1. Installed versus latest versions of `mcp`, `pyyaml`, Python, and this project.
2. Known vulnerabilities in every installed package, using `pip-audit`.
3. The MCP protocol version the installed SDK speaks.
4. Database health: integrity, size, number of ideas, and the age of the last backup.
5. The always-on server, if installed: does it answer?
6. Free disk space where the database lives.

## 1. Set your policy

The policy says when the checkup runs, when to propose upgrades, how long to
wait after a release, and which weeks to avoid. **On the Mini**, from the
project folder:

```bash
mkdir -p ~/.knowledge-mcp
cp maintenance.example.toml ~/.knowledge-mcp/maintenance.toml
open -e ~/.knowledge-mcp/maintenance.toml
```

The defaults:

| Setting | Default | Meaning |
|---|---|---|
| `checkup_day`, `checkup_time` | Monday 08:00 | When the weekly checkup runs |
| `migration_day`, `migration_time` | Saturday 10:00 | When upgrades are proposed |
| `migration_duration_minutes` | 60 | Length of the calendar slot |
| `soak_days` patch / minor / major | 7 / 14 / 30 | Days to wait after a release before proposing it |
| `blackout.dates` | 20 Dec to 4 Jan | Windows that never get a proposal |
| `backup.before_checkup` | true | Back up the database at the start of every checkup |
| `backup.keep_last` | 12 | Backups to keep |

**Why wait after a release:** most problems in a new version surface within
days, and other people find them first. Waiting costs little; being first costs
an evening of debugging.

**How a date is chosen:** the first migration day on or after the release date
plus the waiting period, never earlier than tomorrow, and never inside a
blackout window. A security fix skips the wait: it is proposed for the next
day.

## 2. Run it once by hand

```bash
make checkup
```

Expected, ending with lines like these:

```
Report: /Users/you/.knowledge-mcp/maintenance/report-2026-10-05.md
1 upgrade proposed for Sat Oct 17; DB healthy; backup 0 days old
```

A macOS notification shows the same summary. The checkup writes everything to
`~/.knowledge-mcp/maintenance/`, never into the project folder.

## 3. Schedule it

```bash
deploy/macos/install_launchd.sh install checkup
```

Expected:

```
Using policy: /Users/you/.knowledge-mcp/maintenance.toml
Installed /Users/you/Library/LaunchAgents/com.example.knowledge-mcp-checkup.plist
Scheduled: every Monday at 08:00.
Run it now: launchctl kickstart gui/501/com.example.knowledge-mcp-checkup
```

If the Mini is asleep at that moment, the checkup runs when it wakes. If you
change `checkup_day` or `checkup_time`, run the install command again.

**Check it fires:** run the `launchctl kickstart` line it printed. Within a
minute you should see the notification, and a new report:

```bash
ls -t ~/.knowledge-mcp/maintenance/ | head -3
```

## 4. Read the report

Each report lists every item with a status:

| Status | Meaning |
|---|---|
| 🟢 green | Fine. Nothing to do. |
| 🟡 yellow | Worth a look: an upgrade is available, a lookup failed, or a backup is getting old. |
| 🔴 red | Needs attention: a major upgrade, a known vulnerability, a failed integrity check, or the server not answering. |

The easiest way to read it is to ask Claude. Open Claude Code in the project
folder and type:

```
/checkup
```

Claude reads the newest report and its tickets, explains them in plain
language, and answers questions. It does not change anything.

## 5. Tickets and calendar entries

For each new upgrade, the checkup writes two files:

- `ticket-<package>-<version>.md`: current and target versions, how big a change
  it is, the release date, the proposed date, the changelog link, risk notes, and
  how to roll back.
- `ticket-<package>-<version>.ics`: a calendar entry for the proposed time.

Add the calendar entry by opening it. Calendar asks you to confirm; the
checkup never writes to your calendar itself.

```bash
open ~/.knowledge-mcp/maintenance/ticket-mcp-2.3.0.ics
```

A ticket is written once. Later checkups leave it alone, so notes you or
`/migrate` add are kept.

Two flags change how a ticket is handled:

- **SECURITY:** a known vulnerability has a fix. Proposed for the next day,
  whatever the waiting period. Do not let it wait.
- **PLAN REQUIRED:** a major version, which usually breaks things. `/migrate`
  writes a plan for you to read and will not start until you approve it.

## 6. Carry out an upgrade with /migrate

On the proposed date or later, open Claude Code in the project folder **on the
Mini** and type:

```
/migrate
```

or name the ticket: `/migrate mcp-2.3.0`. Claude then works through a fixed
sequence and tells you what it is doing at each step:

1. Checks the project has no unsaved changes.
2. Picks the ticket, asking you if more than one is open. Security tickets come first.
3. For **PLAN REQUIRED** tickets, writes a plan and stops until you approve it.
4. Backs up the database and confirms the backup is sound.
5. Creates a separate branch, `upgrade/<package>-<version>`. Your working
   version stays untouched on `main`.
6. Reads the upstream changelog and checks whether any breaking change touches
   this code.
7. Updates the version, runs `make check` and `make smoke`.
8. Reports what changed and the test results, then **stops**.

It then asks three separate questions, and acts only on a "yes":

- Merge the upgrade into `main`?
- Restart the always-on service?
- Close the ticket?

If anything fails, Claude restores the previous versions, keeps the branch so
you can look at it, writes what went wrong into the ticket, and proposes a new
date a week later.

**Why the stops:** an upgrade that passes tests can still surprise you. The
stops give you a moment to read the report before anything you depend on
changes.

## 7. Test the whole system without waiting for a release

You can make the checkup pretend a newer version exists. This is how the
project tests itself, and it changes nothing:

```bash
make checkup ARGS="--stub mcp=2.3.0@2026-09-20 --today 2026-10-01"
```

Expected:

```
New ticket: ticket-mcp-2.3.0.md (proposed 2026-10-10)
1 upgrade proposed for Sat Oct 10; DB healthy; backup 0 days old
```

The date follows the rule: released 20 September, minor change, 14 days to
wait, so the first Saturday on or after 4 October is 10 October.

Delete the practice ticket afterward so it does not linger:

```bash
rm ~/.knowledge-mcp/maintenance/ticket-mcp-2.3.0.*
```

## 8. Optional: a plain-language summary without opening Claude Code

This is documented here but **off by default**, and the project never enables
it for you. It adds a second weekly job that asks Claude Code, in its
non-interactive mode, to summarize the latest report into a short file.

Things to know first:

- It uses your Claude account each week, and it sends the report's contents to
  Claude, like any other conversation.
- It is restricted to reading. `--tools` limits Claude to the Read, Glob, and
  Grep tools, `--disallowedTools "mcp__*"` removes every MCP server's tools,
  and `--permission-mode dontAsk` refuses anything that would need approval.
- `--max-turns` and `--max-budget-usd` cap how much work and money one run can use.
- Never run `/migrate` this way. Upgrades need you there.

The command, run from the project folder:

```bash
claude -p "/checkup" \
  --tools "Read,Glob,Grep" \
  --disallowedTools "mcp__*" \
  --permission-mode dontAsk \
  --add-dir ~/.knowledge-mcp/maintenance \
  --max-turns 10 \
  --max-budget-usd 0.50 \
  > ~/.knowledge-mcp/maintenance/summary-$(date +%F).md
```

To schedule it, an hour after the checkup, save this as
`~/Library/LaunchAgents/com.example.knowledge-mcp-summary.plist`, replacing
`/Users/you` with your home folder:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.knowledge-mcp-summary</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd ~/dev/practitioner-knowledge-mcp &amp;&amp; claude -p "/checkup" --tools "Read,Glob,Grep" --disallowedTools "mcp__*" --permission-mode dontAsk --add-dir ~/.knowledge-mcp/maintenance --max-turns 10 --max-budget-usd 0.50 &gt; ~/.knowledge-mcp/maintenance/summary-$(date +%F).md</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardErrorPath</key>
  <string>/Users/you/Library/Logs/knowledge-mcp/summary.err.log</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.knowledge-mcp-summary.plist
```

The flag names were checked against the Claude Code documentation when this
guide was written. If a run fails, `claude --help` shows the current names.

## Turn the checkup off

```bash
deploy/macos/install_launchd.sh uninstall checkup
```

Your policy, reports, and tickets stay where they are.

## If something went wrong

| Symptom | Fix |
|---|---|
| No notification, no new report | `deploy/macos/install_launchd.sh status checkup`, then `tail -20 ~/Library/Logs/knowledge-mcp/checkup.err.log` |
| `Error: checkup_day must be a weekday...` | Fix the named setting in `~/.knowledge-mcp/maintenance.toml` |
| A version line says `lookup failed` | The Mini was offline or a site was down. The next checkup tries again. |
| `pip-audit failed` | Run `make install`, which installs pip-audit, then `make checkup` |
| The project shows `no releases found` | Normal until the repository is public and has a release |
| `/migrate` stops at step 0 | Commit or discard your own changes first, and switch to `main` |
