# Write your own frameworks

Ideas are the things you think. Frameworks are the ways you think: a
pre-mortem, an assumption audit, a business case structure, a negotiation
checklist. Write a framework once, and Claude can pull it into any
conversation with `get_framework`.

## Why Markdown files, not the database

Ideas grow one tool call at a time, so they live in the database. Frameworks
change slowly and deserve careful editing, so they live as plain text files:

- You edit them in any text editor.
- You keep their history in git and see exactly what changed and when.
- You can share one by sending a single file.

The server reads the `frameworks/` folder each time a framework tool runs, so a
new or edited file is available immediately. No restart needed.

## The format

Each framework is one `.md` file. The file name, without `.md`, is the name you
and Claude use to ask for it. Use lowercase words joined by hyphens:
`pre-mortem.md`, `stakeholder-map.md`.

The file starts with a short header between two `---` lines, then the body:

```markdown
---
title: Stakeholder Map
category: analysis
use_when: Before a decision that several groups can delay or block
---
## Purpose

Why this framework exists, and the problem it solves.

## Steps

1. First step.
2. Second step.

## Common failure modes

- What goes wrong when people use it badly.

## Further reading

- Where to learn more.
```

| Header field | Meaning |
|---|---|
| `title` | The display name. Defaults to the file name in title case. |
| `category` | A grouping you choose, such as `stress-test`, `appraisal`, or `analysis`. `list_frameworks` can filter by it. |
| `use_when` | One sentence on when to reach for this framework. Claude reads it to decide which framework fits your question. |

The sample frameworks also carry a `name` line. The server ignores it and uses
the file name, so the two can never disagree.

The four body sections are a convention, not a rule. They work well because
they answer what Claude needs: why, how, what goes wrong, and where to go next.

## Write one

From the project folder:

```bash
cp frameworks/pre-mortem.md frameworks/stakeholder-map.md
open -e frameworks/stakeholder-map.md
```

Replace the header and body with your own content, then save.

Check it:

```bash
make frameworks
```

Expected: one line per framework, including yours:

```
Frameworks in /Users/you/dev/practitioner-knowledge-mcp/frameworks: 4
  assumption-audit | stress-test | When a forecast, model, or recommendation rests on ...
  five-case-business-case-lite | appraisal | When a public or shared investment needs ...
  pre-mortem | stress-test | Before committing capital or political capital to a plan
  stakeholder-map | analysis | Before a decision that several groups can delay or block
```

If your framework is missing, check that the file ends in `.md` and sits
directly inside `frameworks/`, not in a subfolder.

Then, in Claude Desktop:

> Use practitioner-knowledge to list my frameworks, then walk me through the
> stakeholder map for my current project.

## Keep your frameworks somewhere else

You may want your frameworks in their own private git repository, separate
from this project. Point the server at that folder with
`KNOWLEDGE_MCP_FRAMEWORKS`. In Claude Desktop's settings, add it to the `env`
block next to `KNOWLEDGE_MCP_DB`:

```json
"env": {
  "KNOWLEDGE_MCP_DB": "/Users/you/.knowledge-mcp/ideas.db",
  "KNOWLEDGE_MCP_FRAMEWORKS": "/Users/you/frameworks"
}
```

Quit Claude Desktop with Cmd-Q before you edit the file, and reopen it afterward.

## Limits and safety

- The server reads only `.md` files directly inside the frameworks folder.
- It ignores shortcuts (symlinks), so a framework file cannot point at
  something outside the folder.
- It skips files larger than 200 KB. A framework that long should be split.
- `get_framework` accepts only names that exist in the folder. It cannot be
  used to read any other file on your Mac.

## Writing tips

- **Lead with the puzzle.** The Purpose section should name the problem in one
  or two sentences. Claude uses it to judge fit.
- **Make steps concrete.** "List every condition that must hold" beats
  "consider assumptions."
- **Name the failure modes.** They are often the most useful part, because
  they tell Claude what to watch for in your answers.
- **Keep sources honest.** If you adapt a published method, say so in Further
  reading.
