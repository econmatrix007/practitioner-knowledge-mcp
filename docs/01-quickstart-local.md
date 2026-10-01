# Quickstart: run it on your Mac

This guide takes you from nothing to a working knowledge server on one Mac in
about 15 minutes. You will install two tools, download the project, create a
database with sample ideas, and test every tool. Connecting Claude Desktop is
the next guide, [02-connect-claude-desktop.md](02-connect-claude-desktop.md).

You type every command in **Terminal** (Applications, then Utilities, then
Terminal). Paste one command at a time and compare what you see with the
expected output below it. Small differences in numbers and timings are normal.

## 1. Check what you already have

```bash
sw_vers -productVersion
```

Expected: a macOS version number, such as `15.6`. Any currently supported
macOS release works.

```bash
git --version
```

Expected: `git version 2.x`. If macOS offers to install the command line
developer tools instead, click **Install**, wait for it to finish, and run the
command again.

```bash
uv --version
```

Expected: `uv 0.8` or newer. If you see `command not found`, install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then close Terminal, open a new window, and run `uv --version` again. If you
use Homebrew, `brew install uv` works too.

**Why uv:** it installs the right Python version for this project and keeps the
project's packages in their own folder. Nothing touches the Python that came
with your Mac.

## 2. Download the project

```bash
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/OWNER/practitioner-knowledge-mcp.git
cd practitioner-knowledge-mcp
```

Expected: `Cloning into 'practitioner-knowledge-mcp'...` and a few lines of
progress. Every later command in this guide runs from this folder.

## 3. Install

```bash
make install
```

Expected: the first time, uv downloads Python 3.12 and the project's packages.
The last lines look like this:

```
Resolved 48 packages in 20ms
Installed 45 packages in 1.2s
```

This creates a hidden `.venv` folder inside the project. Nothing is installed
anywhere else.

## 4. Create the database and add sample ideas

```bash
make init-db
```

Expected:

```
Database ready: /Users/you/.knowledge-mcp/ideas.db
Schema version: 1. Ideas stored: 0.
```

```bash
make seed
```

Expected:

```
Seeded /Users/you/.knowledge-mcp/ideas.db from sample_ideas.json
Inserted: 12. Skipped (already present): 0.
Ideas stored: 12.
```

The 12 sample ideas are fictional. They exist so you can test searching before
you add your own. Running `make seed` again is safe: it skips ideas that are
already there.

**Your data lives in one file:** `~/.knowledge-mcp/ideas.db`. It is outside the
project folder, so updating or deleting the project never touches it.

## 5. Test every tool

```bash
make smoke
```

This starts the server the same way Claude Desktop will, then calls each
read-only tool. It never changes your data. Expected, ending with:

```
  PASS  get_framework              0.00s
  PASS  database                   12 ideas

12 passed, 0 failed.
```

If any line says FAIL, the output ends with the server's own error message.
That message usually names the problem.

## 6. Optional: explore in MCP Inspector

MCP Inspector is a free tool from the MCP project that shows a server's tools
in your browser and lets you call them by hand. It needs Node.js
(`brew install node`).

```bash
make inspect
```

A browser tab opens.

1. Click **Connect**. The first time, this can time out while the server
   starts. Click **Retry** once; it connects immediately after that.
2. Click **Tools**, then **List Tools**. You should see eight tools.
3. Click `search_ideas`, type `supply chain` in the query field, and click
   **Run Tool**. You should see three results.

Press **Ctrl-C** in Terminal to stop the Inspector.

## What you have now

- A database at `~/.knowledge-mcp/ideas.db` with 12 sample ideas.
- Three sample frameworks in the project's `frameworks/` folder.
- A server that passes every check.

Next: [connect Claude Desktop](02-connect-claude-desktop.md).

## If something went wrong

| Symptom | Fix |
|---|---|
| `make: command not found` | Install the command line developer tools: `xcode-select --install` |
| `uv: command not found` after installing | Open a new Terminal window so it picks up the new PATH |
| `make install` fails while downloading | Check your internet connection and run it again |
| `make smoke` shows FAIL | Read the server log printed below the results; see the [FAQ](faq.md) |
