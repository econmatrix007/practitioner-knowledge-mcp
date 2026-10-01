# Remote access over Tailscale

This guide connects Claude Desktop on your laptop to the knowledge server
running on your always-on Mac mini. Your ideas stay in one database on one
machine, and you can reach them from anywhere.

**Before you start:** the server must already run as a service on the Mac mini.
If it does not, follow [03-always-on-mac-mini.md](03-always-on-mac-mini.md) first.

## Why it works this way

Claude Desktop starts local servers and talks to them over stdio. It cannot
talk to an HTTP server on another machine by itself. Two pieces close the gap:

1. **Tailscale** builds a private, encrypted network between your own devices.
   The server listens only on that private network, never on the public
   internet and never on your office or home Wi-Fi.
2. **mcp-remote** is a small bridge. Claude Desktop starts it like any local
   server. It forwards each request over HTTP to the Mac mini and adds your
   access token to every request.

```
Laptop                                          Mac mini
Claude Desktop --stdio--> mcp-remote --HTTP over Tailscale--> knowledge server --> ideas.db
                          (adds token)          (encrypted)       (checks token)
```

Plain HTTP is acceptable here only because Tailscale already encrypts the
traffic between your devices. Never expose this server to the public
internet, and never turn on Tailscale Funnel for it.

## What you need

| Item | Where |
|---|---|
| Tailscale on both Macs, signed in to the same account | tailscale.com/download or the Mac App Store |
| The server installed as a service on the Mac mini | [03-always-on-mac-mini.md](03-always-on-mac-mini.md) |
| Node.js on the laptop (provides `npx`, which runs mcp-remote) | `brew install node` |
| Claude Desktop on the laptop | claude.ai/download |

Throughout this guide, **Mini** means the Mac mini and **Laptop** means the
machine you carry. Each step says where to type.

## Step 1. Check that both Macs are on your tailnet

The Tailscale app installs a command-line tool. If `tailscale` is not found in
Terminal, add this line to `~/.zshrc`, then open a new Terminal window:

```bash
alias tailscale="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
```

**On either Mac:**

```bash
tailscale status
```

Expected: one line per device, including both Macs. Each line starts with an
address that begins with `100.`. For example:

```
100.101.102.103  mini      you@  macOS  -
100.101.102.104  laptop    you@  macOS  -
```

## Step 2. Find the Mini's Tailscale address and name

**On the Mini:**

```bash
tailscale ip -4
```

Expected: one address, such as `100.101.102.103`. Write it down; this guide
calls it `MINI_IP`.

```bash
tailscale status --json | python3 -c "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))"
```

Expected: a name such as `mini.your-tailnet.ts.net`. This guide calls it
`MINI_NAME`. You can use either the address or the name to reach the Mini.

## Step 3. Move the service onto the Tailscale address

**On the Mini**, from the project folder. Replace `MINI_IP` and `MINI_NAME`
with your values:

```bash
cd ~/dev/practitioner-knowledge-mcp
deploy/macos/install_launchd.sh install server --host MINI_IP --allowed-hosts MINI_NAME
```

Expected:

```
Using existing token: /Users/you/.knowledge-mcp/token
Installed /Users/you/Library/LaunchAgents/com.example.knowledge-mcp.plist
Server is up: http://MINI_IP:8765/healthz
```

What changed, and why:

- The server now listens on the Tailscale address only. Other devices on your
  Wi-Fi cannot reach it.
- `--allowed-hosts` lets clients use the Mini's Tailscale name as well as its
  address. The server rejects requests that name any other host.
- A token is required. The server refuses to listen on a non-local address
  without one.

If macOS asks whether to allow incoming network connections for
`knowledge-mcp` or Python, click **Allow**.

Claude Desktop on the Mini is not affected. It starts its own local copy of the
server over stdio and shares the same database file.

**Check on the Mini:**

```bash
curl -s http://MINI_IP:8765/healthz
```

Expected: `{"status":"ok"}`

## Step 4. Reach the Mini from the Laptop

**On the Laptop:**

```bash
curl -s http://MINI_IP:8765/healthz
```

Expected: `{"status":"ok"}`. If this hangs, Tailscale is not connecting the
two Macs; see Troubleshooting below.

Now confirm the server refuses requests without a token:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://MINI_IP:8765/mcp
```

Expected: `401`. That number means "unauthorized," and it is the answer you want.

## Step 5. Copy the token to the Laptop

The token lives on the Mini at `~/.knowledge-mcp/token`. The Laptop needs it in
a small file that mcp-remote reads. The token never goes into the Claude
Desktop config, and it never appears in the list of running processes.

Universal Clipboard is the simplest path when both Macs use the same Apple
Account with Handoff turned on.

**On the Mini:**

```bash
pbcopy < ~/.knowledge-mcp/token
```

**On the Laptop**, within a minute:

```bash
mkdir -p ~/.knowledge-mcp && chmod 700 ~/.knowledge-mcp
( umask 077; printf 'Authorization: Bearer %s\n' "$(pbpaste | tr -d '[:space:]')" > ~/.knowledge-mcp/remote-headers )
pbcopy < /dev/null
```

The last line clears the clipboard. Clear it on the Mini as well:

```bash
pbcopy < /dev/null
```

If Universal Clipboard is off, AirDrop the
token file from the Mini instead, then run the same `printf` line with
`"$(tr -d '[:space:]' < ~/Downloads/token)"` in place of the `pbpaste` part,
and delete the downloaded copy. Do not send the token by email or chat.

**Check on the Laptop:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H @$HOME/.knowledge-mcp/remote-headers \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}' \
  http://MINI_IP:8765/mcp
```

Expected: `200`. A `401` means the token in the file does not match the Mini's.

## Step 6. Find the Laptop's npx

Claude Desktop does not read your Terminal's PATH, so the config needs the full
path to `npx`.

**On the Laptop:**

```bash
which npx
```

Expected: `/opt/homebrew/bin/npx` on Apple silicon, or `/usr/local/bin/npx` on
Intel Macs. If nothing prints, run `brew install node` and try again.

## Step 7. Add the server to Claude Desktop on the Laptop

The example config is in
[examples/claude_desktop_config.remote.json](../examples/claude_desktop_config.remote.json).
Rather than edit JSON by hand, this command adds the entry for you. It backs up
your config first, leaves every other server untouched, and refuses to
overwrite an existing `practitioner-knowledge` entry.

**On the Laptop.** Replace `MINI_IP` on the first line, then paste the whole
block at once:

```bash
MINI_IP=100.101.102.103 python3 - <<'PYEOF'
import json, os, shutil
p = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
cfg = json.load(open(p)) if os.path.exists(p) else {}
if os.path.exists(p):
    shutil.copy(p, p + ".backup")
servers = cfg.setdefault("mcpServers", {})
if "practitioner-knowledge" in servers:
    raise SystemExit("practitioner-knowledge already exists; nothing changed.")
servers["practitioner-knowledge"] = {
    "command": shutil.which("npx") or "/opt/homebrew/bin/npx",
    "args": [
        "-y", "mcp-remote@0.14.3",
        f"http://{os.environ['MINI_IP']}:8765/mcp",
        "--transport", "http-only",
        "--allow-http",
        "--header-file", os.path.expanduser("~/.knowledge-mcp/remote-headers"),
    ],
}
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print("Added practitioner-knowledge. Servers:", ", ".join(servers))
PYEOF
```

Expected: `Added practitioner-knowledge. Servers: ...` followed by your server names.

Why each argument is there:

| Argument | Purpose |
|---|---|
| `mcp-remote@0.14.3` | A pinned version, so the bridge never changes without you knowing. |
| `--transport http-only` | Use Streamable HTTP. This server does not offer the older SSE transport. |
| `--allow-http` | mcp-remote expects HTTPS by default. Tailscale already encrypts this link. |
| `--header-file` | Reads the token from the file you made in Step 5. |

Quit Claude Desktop completely with **Cmd-Q**, then reopen it.

## Step 8. Test from the Laptop

In a new chat, ask:

> Use practitioner-knowledge to search my ideas for supply chain.

Expected: Claude calls `search_ideas` and describes the ideas stored on the
Mini. Anything you store from the Laptop now lands in the Mini's database.

**Check the bridge log on the Laptop:**

```bash
grep -m1 "Connected to remote server" ~/Library/Logs/Claude/mcp-server-practitioner-knowledge.log
```

Expected: a line ending in `Connected to remote server using StreamableHTTPClientTransport`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Step 4 `curl` hangs | Tailscale is off on one Mac, or they use different accounts | Open the Tailscale app on both Macs and run `tailscale status` |
| `curl` says "connection refused" | The service is not listening on `MINI_IP` | On the Mini: `tail -30 ~/Library/Logs/knowledge-mcp/server.err.log` |
| Works at first, fails after the Mini restarts | Tailscale came up after the server | Nothing to do: launchd retries every 10 seconds until it can bind |
| Log shows `Missing or invalid bearer token` | The Laptop's token does not match the Mini's | Repeat Step 5 |
| Log shows `Discovering OAuth server configuration` and a browser opens | Same as above: mcp-remote tried to log in because the token was refused | Repeat Step 5, then quit and reopen Claude Desktop |
| Claude Desktop shows a timeout the first time | `npx` is downloading mcp-remote | Wait a minute and click Retry |
| Log shows `Invalid Host header` on the Mini | You connected by a name not in `--allowed-hosts` | Re-run Step 3 with that name in `--allowed-hosts` |

## Change the token

Do this if the token may have leaked, or once a year as routine care.

**On the Mini:**

```bash
rm ~/.knowledge-mcp/token
deploy/macos/install_launchd.sh install server --host MINI_IP --allowed-hosts MINI_NAME
```

Expected: `Created token: ...` and `Server is up: ...`. Then repeat Step 5 on
every Laptop. Old tokens stop working immediately.

## Stop remote access

**On the Mini**, move the service back to local-only:

```bash
deploy/macos/install_launchd.sh install server
```

Expected: `Server is up: http://127.0.0.1:8765/healthz`. Laptops can no longer
connect. Remove the `practitioner-knowledge` entry from the Laptop's Claude
Desktop config and delete `~/.knowledge-mcp/remote-headers` there.
