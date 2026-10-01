# Security policy

## Reporting a vulnerability

Please report security problems privately. Do not open a public issue.

1. **Preferred:** use GitHub's private reporting. On the repository page, open
   the **Security** tab and click **Report a vulnerability**.
2. **Or email:** econmatrix@gmail.com

Include what you found, how to reproduce it, and what an attacker could do
with it. You will get an acknowledgment when the maintainer sees the report.
This is a volunteer project, so responses are best effort with no guaranteed
time, but security reports come first.

Please give the maintainer a reasonable time to fix the problem before you
disclose it publicly.

## Supported versions

Only the latest release receives security fixes. Upgrade before reporting a
problem in an older version.

## Scope

In scope:

- The server in `src/knowledge_mcp/`, including its HTTP transport, input
  validation, and framework file access
- The scripts in `scripts/` and `deploy/`
- The example configurations in `examples/`

Out of scope:

- Prompt injection through content you store or frameworks you add. This is a
  known property of AI assistants; see [docs/08-security.md](docs/08-security.md)
  for how to reduce the risk.
- Plugins you write or install. They run with your permissions by design.
- Problems in the MCP SDK, mcp-remote, Tailscale, or Claude Desktop. Report
  those to their own projects.
- Setups that ignore the documented safeguards, such as exposing the server to
  the public internet.

## No telemetry

The project collects no usage data, sends nothing to the maintainer, and makes
only the read-only version checks listed below.

These checks run only in the maintenance checkup, when you run it or schedule
it:

| Check | Where it asks | What it sends |
|---|---|---|
| Latest versions of `mcp` and `pyyaml` | The PyPI JSON API | The package names |
| Latest release of this project | The GitHub releases API | The project's name |
| Latest Python release | python.org | Nothing beyond the request |
| Known vulnerabilities | The advisory database `pip-audit` queries | Names and versions of installed packages |

The server itself makes no outbound network requests.

## Security design in brief

- The HTTP service listens on `127.0.0.1` by default. It refuses all-interfaces
  addresses unless explicitly allowed, and refuses any non-local address
  without a bearer token.
- DNS rebinding protection is always on.
- Tokens are compared in constant time and stored only in files readable by
  their owner.
- All SQL uses placeholders. Inputs are validated and capped.
- Framework reads are limited to an allow-list built from the frameworks
  folder; symlinks and path tricks are refused.
- No tool runs shell commands, fetches URLs, or deletes data.

Details: [docs/08-security.md](docs/08-security.md).
