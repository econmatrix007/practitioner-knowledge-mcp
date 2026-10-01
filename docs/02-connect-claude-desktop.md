# Connect Claude Desktop

This guide adds the knowledge server to Claude Desktop on the same Mac. When
you finish, you can ask Claude to search, store, and update your ideas in any
chat. Finish the [Quickstart](01-quickstart-local.md) first.

## How the connection works

Claude Desktop reads a small settings file when it starts. Each entry in that
file names a program to launch. Claude Desktop starts the program in the
background and talks to it through its input and output streams (called
"stdio"). No network port is opened.

The settings file lives here:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

It may already list other servers. The steps below add one entry and leave
everything else alone.

## 1. Find two paths

Claude Desktop does not read your Terminal's settings, so it needs full paths.

```bash
which uv
```

Expected: a path such as `/Users/you/.local/bin/uv` or `/opt/homebrew/bin/uv`.

```bash
cd ~/dev/practitioner-knowledge-mcp && pwd
```

Expected: `/Users/you/dev/practitioner-knowledge-mcp`.

## 2. Add the entry

The example entry is in
[examples/claude_desktop_config.stdio.json](../examples/claude_desktop_config.stdio.json).
You can paste it by hand, but one missing comma breaks the whole file. This
command adds the entry for you. It backs up your settings first, never changes
other entries, and refuses to overwrite an existing `practitioner-knowledge`
entry.

Run it from the project folder, and paste the whole block at once:

```bash
python3 - <<'PYEOF'
import json, os, shutil
p = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
cfg = json.load(open(p)) if os.path.exists(p) else {}
if os.path.exists(p):
    shutil.copy(p, p + ".backup")
servers = cfg.setdefault("mcpServers", {})
if "practitioner-knowledge" in servers:
    raise SystemExit("practitioner-knowledge already exists; nothing changed.")
servers["practitioner-knowledge"] = {
    "command": shutil.which("uv") or os.path.expanduser("~/.local/bin/uv"),
    "args": ["--directory", os.getcwd(), "run", "knowledge-mcp", "--transport", "stdio"],
    "env": {"KNOWLEDGE_MCP_DB": os.path.expanduser("~/.knowledge-mcp/ideas.db")},
}
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print("Added practitioner-knowledge. Servers:", ", ".join(servers))
PYEOF
```

Expected: `Added practitioner-knowledge. Servers:` followed by the names of all
your servers.

Check that the file is still valid:

```bash
python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json > /dev/null && echo valid
```

Expected: `valid`

## 3. Restart Claude Desktop

Quit Claude Desktop completely with **Cmd-Q**. Closing the window is not
enough, because the app keeps running in the background. Then open it again.

Claude Desktop starts the server and writes a log. Check that the log exists:

```bash
ls ~/Library/Logs/Claude/ | grep practitioner
```

Expected: `mcp-server-practitioner-knowledge.log`

If the list is empty, Claude Desktop did not read the new entry. Make sure you
quit with Cmd-Q, then try again.

## 4. Try it

Open a new chat and ask:

> Use practitioner-knowledge to search my ideas for supply chain.

Claude may ask permission to use the `search_ideas` tool. Allow it. A correct
answer describes three sample ideas: supplier lead-time variance, inventory
buffers at the chokepoint, and dual sourcing as insurance.

Then try storing something:

> Store a new idea in practitioner-knowledge. Title: "Meeting length expands to
> fill the calendar slot". Domain: strategy. Problem: meetings run long even
> when the agenda is short. Insight: default slot lengths anchor expectations;
> shorter defaults cut meeting time without cutting outcomes.

Claude calls `store_idea` and reports the new idea's number.

## The eight tools

| Tool | What it does |
|---|---|
| `store_idea` | Saves a new idea: title, domain, problem, insight, and optional assumptions, tags, and status |
| `get_idea` | Shows one idea in full |
| `update_idea` | Changes any fields of an existing idea |
| `search_ideas` | Full-text search, best match first |
| `list_ideas` | Lists ideas, newest first, filtered by domain, tag, or status |
| `idea_stats` | Counts by domain and status, plus the most used tags |
| `list_frameworks` | Lists your analytical frameworks |
| `get_framework` | Shows one framework in full |

Ideas move through five statuses: `seed`, `developing`, `mature`, `published`,
and `archived`. Nothing is ever deleted by a tool; archive an idea instead.

## Tips

- **Name the server in your prompt** when you have several connected, as in
  "Use practitioner-knowledge to...". Two servers can offer tools with the same
  name, and naming the server removes any doubt.
- **The first connection can be slow.** If Claude Desktop reports a timeout the
  very first time, uv was still setting up. Click Retry.
- **Keep private and public servers apart when sharing.** If you take
  screenshots or copy chats for others, use a chat where only the server you
  mean to show is turned on.

## If something went wrong

| Symptom | Fix |
|---|---|
| No `mcp-server-practitioner-knowledge.log` | The entry is missing or Claude Desktop was not fully quit. Repeat steps 2 and 3. |
| Claude says it has no such tool | Open Settings, then Connectors or Developer, and check that practitioner-knowledge is enabled |
| A red error badge on the server | Read the log: `tail -40 ~/Library/Logs/Claude/mcp-server-practitioner-knowledge.log` |
| `spawn uv ENOENT` in the log | The `command` path is wrong. Run `which uv` and fix the path in the settings file. |
| You want to undo everything | Restore the backup: `cp ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup ~/Library/Application\ Support/Claude/claude_desktop_config.json` |

Next: run it on an [always-on Mac mini](03-always-on-mac-mini.md), or
[make it yours](06-write-your-own-frameworks.md).
