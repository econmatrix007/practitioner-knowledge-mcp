# Contributing

Thank you for helping. This project is a teaching template for people who are
not programmers, so clarity and safety matter more than features. Small,
focused pull requests are the easiest to review and the most likely to merge.

## What fits

**Welcome:**

- Fixes to the guides: a step that did not match what you saw, a missing
  command, a confusing sentence
- Bug fixes with a test that fails before the fix and passes after
- Security hardening
- Items on the roadmap in the [README](README.md#roadmap); open an issue first
  to agree on the approach

**Please do not send:**

- New core tools for a particular field (tax, zoning, legal research). The core
  stays at eight generic tools. Domain tools belong in plugins; see
  [docs/05-add-your-own-tools.md](docs/05-add-your-own-tools.md).
- Real names of people, clients, agencies, programs, or deals in examples or
  sample data. All examples are fictional.
- Tools that run shell commands, fetch URLs, or delete data.
- Telemetry or analytics of any kind.

## Set up

```bash
git clone https://github.com/econmatrix007/practitioner-knowledge-mcp.git
cd practitioner-knowledge-mcp
make install
make hooks
```

`make hooks` installs the pre-commit checks: gitleaks, ruff, and a block on
database and private files.

## Before every commit

```bash
make check
```

This runs the privacy check, the linter, the formatter check, all tests, and
the pre-commit hooks. It must pass. If you publish a fork, copy
`.private-terms.example.txt` to `.private-terms.txt`, list your private names
in it, and run `make release-check` before you push.

## Conventions

- **Python:** 3.12+, type hints throughout, `ruff` for linting and formatting
  (`make format` fixes most issues).
- **Tests:** `pytest`. Each test uses a throwaway database; never point a test
  at a real one.
- **SQL:** placeholders (`?`) only. Never build SQL from strings.
- **Tool descriptions:** plain statements of what the tool does. No
  instructions aimed at the model.
- **Errors:** raise `ToolError` with a clear message. Never return a stack trace.
- **Commits:** one logical change each, with a
  [conventional commit](https://www.conventionalcommits.org) message such as
  `fix(http): ...` or `docs: ...`.

## Writing docs

The readers are domain experts, not developers.

- Plain, active, short sentences. Explain why before how.
- One command per code block where you can, followed by its expected output.
- Say which machine to type on when more than one is involved.
- No em-dashes and no hype.
- Run every command you document before you write it down.

`tests/test_docs.py` checks links, `make` targets, and required wording, so
`make check` catches most mistakes.

## Pull requests

1. Open an issue first for anything larger than a small fix.
2. Keep the pull request to one change.
3. Describe what changed and how you tested it.
4. Confirm `make check` passes.

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE), the same license as the project.

## Code of conduct

Everyone who takes part agrees to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
