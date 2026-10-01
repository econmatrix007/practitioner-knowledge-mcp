# Always on: run the server on a Mac mini

A Mac mini that never sleeps can hold your one knowledge base and serve it to
every device you own. This guide turns the server into a background service
that starts at login, restarts itself if it stops, and keeps logs.

## Why bother

- **One source of truth.** Every device reads and writes the same database.
  Two copies on two laptops drift apart, and merging them later is slow work.
- **Always available.** Your laptop can sleep, travel, or be replaced. The
  knowledge base stays put.
- **Low cost.** A Mac mini idles at a few watts.

If you only ever use one Mac, you do not need this guide. The setup in
[02-connect-claude-desktop.md](02-connect-claude-desktop.md) is enough.

## 1. Keep the Mini awake and ready after power loss

**On the Mini**, open System Settings, then Energy, and turn on:

- **Prevent automatic sleeping when the display is off**
- **Start up automatically after a power failure**

The same settings from Terminal:

```bash
sudo pmset -a sleep 0
sudo pmset -a autorestart 1
pmset -g | grep -E "^ (sleep|autorestart) "
```

Expected from the last command (extra notes in parentheses are normal):

```
 sleep                0
 autorestart          1
```

## 2. Decide how the Mini logs in after a restart

The service is a launchd **agent**. Agents run inside your login session, so
the server starts when you log in and stops when you log out. That keeps it
running as you, with access only to your files.

After a power cut or a software update, the Mini restarts and waits at the
login screen. Choose one:

| Option | Trade-off |
|---|---|
| **Log in by hand after each restart** (recommended) | Keeps FileVault disk encryption on. The server is down until you log in, so use Screen Sharing or walk over. |
| **Turn on automatic login** (System Settings, then Users & Groups) | The server comes back on its own. macOS only allows this with FileVault off, which leaves the disk unencrypted. |

An uninterruptible power supply (UPS) makes restarts rare either way, and it
protects the database from being cut off mid-write.

## 3. Install the project on the Mini

If you have not already, follow the [Quickstart](01-quickstart-local.md) on the
Mini, through `make smoke`.

## 4. Install the service

**On the Mini**, from the project folder:

```bash
deploy/macos/install_launchd.sh install server
```

Expected:

```
Created token: /Users/you/.knowledge-mcp/token (readable only by you)
Installed /Users/you/Library/LaunchAgents/com.example.knowledge-mcp.plist
Server is up: http://127.0.0.1:8765/healthz
```

What the installer did:

1. Created a random access token in `~/.knowledge-mcp/token`. Only your user
   account can read it. Clients must send it with every request.
2. Checked your settings with the server's own rules before changing anything.
3. Wrote the service definition to `~/Library/LaunchAgents/`. It stores the
   token file's location, never the token itself.
4. Started the service and waited until it answered.

The service listens only on this Mac (`127.0.0.1`), on port 8765. To reach it
from other devices, follow [04-remote-access-tailscale.md](04-remote-access-tailscale.md).

## 5. Check it

```bash
curl -s http://127.0.0.1:8765/healthz
```

Expected: `{"status":"ok"}`

```bash
deploy/macos/install_launchd.sh status server
```

Expected: lines including `state = running` and a `pid`.

**Check that it restarts itself.** Stop the server process:

```bash
pkill -f '.venv/bin/knowledge-mcp --transport http'
```

Wait 15 seconds (launchd waits 10 seconds between restarts), then:

```bash
curl -s http://127.0.0.1:8765/healthz
```

Expected: `{"status":"ok"}` again, from a new process.

## 6. Where things live

| What | Where |
|---|---|
| Your ideas | `~/.knowledge-mcp/ideas.db` |
| Access token | `~/.knowledge-mcp/token` |
| Service definition | `~/Library/LaunchAgents/com.example.knowledge-mcp.plist` |
| Server log | `~/Library/Logs/knowledge-mcp/server.err.log` |
| Frameworks | `frameworks/` in the project folder |

Read the latest log lines:

```bash
tail -30 ~/Library/Logs/knowledge-mcp/server.err.log
```

## 7. Claude Desktop on the Mini

Claude Desktop on the Mini can keep the local setup from
[02-connect-claude-desktop.md](02-connect-claude-desktop.md). It starts its own
copy of the server, and both copies share the same database file safely.

## 8. Update the Mini safely

The Mini holds your real data, so treat updates with care. Test a new version
on another Mac first, then:

```bash
cd ~/dev/practitioner-knowledge-mcp
scripts/backup_db.sh
git fetch --tags
git checkout v0.1.1
make install && make check
launchctl kickstart -k gui/$(id -u)/com.example.knowledge-mcp
curl -s http://127.0.0.1:8765/healthz
```

Replace `v0.1.1` with the release you tested. The backup step is covered in
[07-backup-and-single-source-of-truth.md](07-backup-and-single-source-of-truth.md).
The weekly checkup in [09-maintenance-and-upgrades.md](09-maintenance-and-upgrades.md)
tells you when a new version is ready and proposes a date.

The service runs the program installed in the project's `.venv` folder. It
never downloads or upgrades anything when the Mini restarts.

## 9. Change settings or remove the service

Run the installer again with new options; it replaces the old service. Options:

| Option | Meaning |
|---|---|
| `--host ADDR` | Address to listen on. Default `127.0.0.1`. Never `0.0.0.0`. |
| `--port N` | Port. Default `8765`. |
| `--allowed-hosts LIST` | Extra host names clients may use, comma-separated. |
| `--plugins LIST` | Plugin modules or `.py` files to load. See [05-add-your-own-tools.md](05-add-your-own-tools.md). |
| `--db PATH` | Database file. Default `~/.knowledge-mcp/ideas.db`. |
| `--dry-run` | Show the service definition and stop. Changes nothing. |

Remove the service:

```bash
deploy/macos/install_launchd.sh uninstall server
```

Expected: `Removed com.example.knowledge-mcp. Your database, token, and logs were left in place.`
