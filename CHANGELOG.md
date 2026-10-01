# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [0.1.0] - 2026-10-01

The first release: a personal knowledge server for Claude, with guides written
for practitioners rather than programmers.

### Added

- **Eight MCP tools.** Six for ideas (`store_idea`, `get_idea`, `update_idea`,
  `search_ideas`, `list_ideas`, `idea_stats`) and two for frameworks
  (`list_frameworks`, `get_framework`).
- **SQLite storage** with an FTS5 full-text index over title, domain, problem,
  insight, assumptions, and tags. Search ranks by BM25 and falls back from
  all words to any word. Forward-only schema migrations.
- **Markdown frameworks** with YAML front matter, read from an allow-list built
  from the frameworks folder. Three examples: pre-mortem, assumption audit, and
  a five-case business case.
- **Two transports.** stdio for Claude Desktop, and Streamable HTTP for an
  always-on host, on the official MCP Python SDK 2.x (`MCPServer`).
- **Plugins.** Extra tool modules load from `KNOWLEDGE_MCP_PLUGINS`. A broken
  plugin is skipped, and plugins cannot replace core tools.
- **launchd service** for an always-on Mac mini: starts at login, restarts on
  exit, keeps the token out of the service file.
- **Remote access over Tailscale** through the `mcp-remote` bridge, with the
  token read from a private header file.
- **Weekly maintenance checkup.** Checks versions, vulnerabilities
  (`pip-audit`), database health, backup age, the server, and disk space;
  proposes dates under a soak-and-blackout policy; writes reports, tickets, and
  calendar files; sends a macOS notification. It never installs or upgrades.
- **Claude Code commands.** `/checkup` explains the latest report. `/migrate`
  carries out one ticket on a branch and stops for approval before merging,
  restarting, or closing.
- **Scripts and make targets** for install, seeding, backups (online SQLite
  backup with integrity check), smoke tests, MCP Inspector, and framework listing.
- **Guides.** Quickstart, Claude Desktop, always-on Mac mini, Tailscale remote
  access, plugins, frameworks, backups, security, maintenance, and an FAQ.
- **Project files.** SECURITY, SUPPORT, CONTRIBUTING, CODE_OF_CONDUCT
  (Contributor Covenant 2.1), issue templates, and CI on macOS and Ubuntu.

### Security

- The HTTP server binds to `127.0.0.1` by default, refuses `0.0.0.0` and `::`
  unless explicitly allowed, and refuses any non-local address without a
  bearer token.
- DNS rebinding protection is always on, including on Tailscale addresses.
- Bearer tokens are compared in constant time and stored in owner-only files.
- Parameterized SQL, capped inputs, and no tool that runs shell commands,
  fetches URLs, or deletes data.
- `scripts/check_private.sh` scans files, file names, commit messages, refs,
  and full git history for deny-listed terms (printed masked), blocks private
  and database files, and runs gitleaks with a rule for leaked bearer headers.
- No telemetry. The project collects no usage data, sends nothing to the
  maintainer, and makes only the read-only version checks listed in SECURITY.md.

### Known limitations

- macOS is the supported platform. Linux runs the server and tests; Windows is
  not supported.
- One user per database. There are no accounts or permissions.
- No import, export, or tag-management tools yet (see the roadmap in the README).

[0.1.0]: https://github.com/OWNER/practitioner-knowledge-mcp/releases/tag/v0.1.0
