# Support

This is a free project maintained by one volunteer. Support is **best effort**:
there is no service level, no guaranteed response time, and no guarantee of a
response at all.

## Before you ask

Most problems are covered in the guides. Each one ends with a troubleshooting
table:

| Problem area | Guide |
|---|---|
| Installing, `make smoke` failing | [docs/01-quickstart-local.md](docs/01-quickstart-local.md) |
| Claude Desktop not connecting | [docs/02-connect-claude-desktop.md](docs/02-connect-claude-desktop.md) |
| The always-on service | [docs/03-always-on-mac-mini.md](docs/03-always-on-mac-mini.md) |
| Reaching the Mini from a laptop | [docs/04-remote-access-tailscale.md](docs/04-remote-access-tailscale.md) |
| Plugins | [docs/05-add-your-own-tools.md](docs/05-add-your-own-tools.md) |
| Everything else | [docs/faq.md](docs/faq.md) |

## Asking for help

Open an issue with the **Setup help** template. Include:

- The guide and step where you got stuck
- The command you ran and its full output
- Your macOS version (`sw_vers -productVersion`)
- The output of `make smoke`

**Before you paste anything, remove private content:** idea text, names,
tokens, and the contents of `~/.knowledge-mcp/`. Never paste your token or
your `remote-headers` file.

For a bug in the code itself, use the **Bug report** template. For a security
problem, do not open an issue; see [SECURITY.md](SECURITY.md).

## What is out of scope

- Windows setups
- Changes to your own plugins or frameworks
- Help with Claude Desktop, Tailscale, or macOS beyond what the guides cover

## Sponsorship and support

Sponsoring the project does not buy support or change these terms.
Sponsorships are not tax-deductible donations.
