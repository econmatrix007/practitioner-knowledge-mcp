# Add your own tools

The eight core tools cover storing, finding, and reading ideas and frameworks.
Your practice may need more: a tool that drafts a memo outline from an idea, a
review queue, a calculator you use every week. This guide shows how to add a
tool without changing the project's own code.

## How plugins work

A plugin is one Python file with a `register` function. The server imports it
at startup, after the eight core tools, and calls `register` once. Inside
`register` you define tools with `@app.tool()`, exactly as the core tools do.

Three rules keep plugins safe for the rest of the server:

- **Core tools always win.** If a plugin defines a tool with a core tool's
  name, the server keeps the core tool and ignores the plugin's.
- **A broken plugin is skipped.** If a plugin fails to load, the server logs
  the error and starts without it. The core tools keep working.
- **Plugins run with your permissions.** A plugin can do anything your user
  account can do. Only load code you wrote or have read.

## 1. Try the example plugin

The project ships one plugin,
[examples/example_plugin.py](../examples/example_plugin.py). It adds a tool,
`idea_as_markdown`, that formats one idea as a Markdown note.

From the project folder:

```bash
KNOWLEDGE_MCP_PLUGINS=$PWD/examples/example_plugin.py make smoke
```

Expected: the tool list now includes `idea_as_markdown`, and every check passes:

```
  PASS  8 core tools present       get_framework, get_idea, idea_as_markdown, idea_stats, ...
12 passed, 0 failed.
```

## 2. Write your own

This plugin adds a review queue: ideas still marked `developing` that nobody
has touched in a while. It is 25 lines.

Create a folder for your own tools outside the project, so updates never
overwrite them:

```bash
mkdir -p ~/knowledge-tools
open -e ~/knowledge-tools/review_queue.py
```

Paste this, save, and close:

```python
"""Plugin: ideas still in development that have not been updated recently."""

from mcp.server.mcpserver.exceptions import ToolError

from knowledge_mcp import db


def register(app, settings):
    @app.tool(title="Review queue")
    def review_queue(days: int = 30, limit: int = 10) -> dict:
        """List ideas with status 'developing' not updated in the last `days` days,
        oldest first."""
        if not 1 <= days <= 3650 or not 1 <= limit <= 100:
            raise ToolError("days must be 1 to 3650 and limit 1 to 100.")
        conn = db.connect(settings.db_path)
        try:
            rows = conn.execute(
                "SELECT id, title, domain, updated_at FROM ideas "
                "WHERE status = 'developing' AND updated_at < datetime('now', ?) "
                "ORDER BY updated_at LIMIT ?",
                (f"-{days} days", limit),
            ).fetchall()
        finally:
            conn.close()
        return {"count": len(rows), "results": [dict(r) for r in rows]}
```

What each part does:

- `register(app, settings)` is the hook the server calls. `settings` holds the
  database path, so your tool uses the same database as the core tools.
- The docstring becomes the description Claude reads. Describe what the tool
  does in plain words. Do not put instructions to Claude in it.
- The type hints (`days: int = 30`) tell Claude which inputs the tool accepts.
- The SQL uses `?` placeholders. Never build SQL by pasting text together; it
  lets a crafted input change your query.
- `ToolError` sends a clear message back to Claude instead of a crash.
- Each call opens and closes its own connection. The server runs tools on
  worker threads, and a connection cannot be shared between threads.

Test it:

```bash
cd ~/dev/practitioner-knowledge-mcp
KNOWLEDGE_MCP_PLUGINS=~/knowledge-tools/review_queue.py make smoke
```

Expected: `review_queue` appears in the tool list, and every check passes.

## 3. Load it in Claude Desktop

Quit Claude Desktop with **Cmd-Q** first. Then add the plugin to the `env` block
of the server's entry in Claude Desktop's
settings file. This command does it for you and backs up the file first:

```bash
python3 - <<'PYEOF'
import json, os, shutil
p = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
shutil.copy(p, p + ".backup")
cfg = json.load(open(p))
entry = cfg["mcpServers"]["practitioner-knowledge"]
entry.setdefault("env", {})["KNOWLEDGE_MCP_PLUGINS"] = os.path.expanduser("~/knowledge-tools/review_queue.py")
json.dump(cfg, open(p, "w"), indent=2)
print("Plugins:", entry["env"]["KNOWLEDGE_MCP_PLUGINS"])
PYEOF
```

Open Claude Desktop again. Then ask:

> Use practitioner-knowledge to show my review queue.

To load several plugins, separate their paths with commas.

## 4. Load it on the always-on Mini

Pass the same path to the service installer:

```bash
deploy/macos/install_launchd.sh install server --plugins ~/knowledge-tools/review_queue.py
```

Add the `--host` and `--allowed-hosts` options you used before, if any. The
installer replaces the service with one that loads your plugin.

## If a plugin does not appear

The server logs every plugin it loads or skips. In Claude Desktop:

```bash
grep -i plugin ~/Library/Logs/Claude/mcp-server-practitioner-knowledge.log | tail -5
```

On the always-on Mini:

```bash
grep -i plugin ~/Library/Logs/knowledge-mcp/server.err.log | tail -5
```

| Log message | Meaning |
|---|---|
| `Loaded plugin '...'` | Working. If the tool is still missing, restart Claude Desktop. |
| `failed to load and was skipped` | The lines after it show the Python error and the line number. |
| `plugin has no register(app, settings) function` | The file needs a function named exactly `register`. |
| `Tool already exists: ...` | Your tool reuses a name. Rename it. |

## Good habits

- Keep each plugin small and focused. One tool per file is fine.
- Keep your plugins in git, in their own folder or repository.
- Follow the core rules: validate inputs, use `?` placeholders, return
  JSON-friendly results, and report problems with `ToolError`.
- Avoid tools that run shell commands or fetch web pages unless you have
  thought through what a malicious idea or document could make them do. See
  [08-security.md](08-security.md).
