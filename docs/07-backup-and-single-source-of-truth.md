# Backups and a single source of truth

Your knowledge base is one file: `~/.knowledge-mcp/ideas.db`. This guide covers
how to keep exactly one live copy of it, how to back it up, and how to restore
it.

## One database, one host

Keep one live database, on one machine. Connect every other device to it.

The tempting alternative is a copy on each laptop, synced by iCloud Drive,
Dropbox, or a USB stick. It fails in two ways:

1. **Drift.** You add ideas on the laptop, and different ideas on the desktop.
   Neither copy is complete, and merging them by hand takes hours.
2. **Corruption.** SQLite writes to the main file and to two helper files
   (`ideas.db-wal` and `ideas.db-shm`). A sync service that copies one file
   without the others, or copies in the middle of a write, can leave a
   database that will not open.

So: never put the live database in a synced folder. Run it on one Mac (the
always-on Mini, see [03-always-on-mac-mini.md](03-always-on-mac-mini.md)), and
connect other devices over Tailscale
([04-remote-access-tailscale.md](04-remote-access-tailscale.md)). Put the
**backups** wherever you like, including synced folders, because backups are
finished files that nothing writes to.

## Back up

```bash
cd ~/dev/practitioner-knowledge-mcp
scripts/backup_db.sh
```

Expected:

```
Backup OK: /Users/you/.knowledge-mcp/backups/ideas-2026-10-01-144549.db (12 ideas, 64 KB, integrity ok)
Keeping 1 of the newest backups in /Users/you/.knowledge-mcp/backups
```

What the script does:

1. Takes a consistent snapshot with SQLite's own backup feature. It is safe to
   run while the server and Claude Desktop are using the database.
2. Checks the copy with SQLite's integrity check. If the check fails, it keeps
   nothing and says so.
3. Keeps the 12 newest backups and deletes older ones. Change the number with
   `--keep 30`.

Backups are readable only by your user account.

**When to back up:**

- Before every upgrade. The update steps in
  [03-always-on-mac-mini.md](03-always-on-mac-mini.md) start with a backup.
- Weekly. The scheduled checkup in
  [09-maintenance-and-upgrades.md](09-maintenance-and-upgrades.md) does this
  for you.
- Before any bulk change, such as importing or retagging many ideas.

**A second copy elsewhere.** Backups on the same disk do not survive a dead
disk. Turn on Time Machine for the Mini, or copy the backups folder to an
external drive now and then:

```bash
cp -R ~/.knowledge-mcp/backups /Volumes/YourDrive/knowledge-backups
```

## Restore

Restoring replaces the live database with a backup. Stop everything that uses
the database first, so nothing writes to it halfway through.

**1. Stop the always-on service and Claude Desktop.** Quit Claude Desktop with
Cmd-Q. Then, if the service is installed:

```bash
launchctl bootout gui/$(id -u)/com.example.knowledge-mcp
```

**2. Pick a backup.**

```bash
ls -1 ~/.knowledge-mcp/backups/
```

**3. Set the current database aside.** Nothing is deleted. Replace the date in
the last line with the backup you chose:

```bash
cd ~/.knowledge-mcp
mkdir -p replaced
mv ideas.db ideas.db-wal ideas.db-shm replaced/ 2>/dev/null; ls replaced/
cp backups/ideas-2026-10-01-144549.db ideas.db
```

**4. Check the restored database.**

```bash
cd ~/dev/practitioner-knowledge-mcp && make init-db
```

Expected: `Database ready: ...` and the number of ideas in that backup.

**5. Start the service again** and reopen Claude Desktop:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.knowledge-mcp.plist
curl -s http://127.0.0.1:8765/healthz
```

Expected: `{"status":"ok"}`

Once you are sure the restore is right, you can delete
`~/.knowledge-mcp/replaced/`.

## Frameworks belong in git

Frameworks are text files in the project's `frameworks/` folder, or in your
own folder (see [06-write-your-own-frameworks.md](06-write-your-own-frameworks.md)).
Git is their backup and their history:

```bash
cd ~/dev/practitioner-knowledge-mcp
git add frameworks/
git commit -m "Add stakeholder map framework"
```

If your frameworks are private, keep them in a separate private repository and
point `KNOWLEDGE_MCP_FRAMEWORKS` at it. Do not commit private frameworks to a
public fork of this project.
