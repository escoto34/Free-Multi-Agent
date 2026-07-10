# MultiAgent skills

External skills extend the interactive chat with reusable instruction packs
(similar to Claude/Grok `SKILL.md` plugins).

## Format

Point MultiAgent at a **directory** containing `SKILL.md` (or at the file itself).

```text
my-skill/
└── SKILL.md
```

`SKILL.md` **must** start with YAML frontmatter:

```markdown
---
name: ponytail
description: One-line (or short paragraph) of when to use this skill.
version: "1.0"
---

# Title

Markdown instructions the model should follow when the skill is **enabled**.
```

| Field | Required | Rules |
|-------|----------|--------|
| `name` | yes | lowercase `[a-z0-9_-]`, 1–64 chars |
| `description` | yes | non-empty |
| `version` | no | free string, default `1.0` |
| body | yes | markdown after the closing `---`, ≥ ~20 chars |

## Global registry

Skills are registered in:

```text
~/.config/multiagent/skills.yaml
```

That file is independent of your current working directory, so enable/disable
works anywhere you run `multiagent`.

Example registry entry:

```yaml
skills:
  ponytail:
    path: /home/you/skills/ponytail
    enabled: true
    skill_md: /home/you/skills/ponytail/SKILL.md
```

## CLI

```bash
# Register (validates format first)
multiagent skills add /path/to/ponytail
multiagent skills add ./skills/example-ponytail --disabled

# List / show
multiagent skills list
multiagent skills show ponytail

# Toggle from any directory
multiagent skills enable ponytail
multiagent skills disable ponytail

# Unregister (does not delete files on disk)
multiagent skills remove ponytail
```

Inside the TUI (`multiagent` chat):

```text
/skills
/skills add /path/to/skill
/skills enable ponytail
/skills disable ponytail
/skills show ponytail
/skills remove ponytail
```

## Runtime behaviour

When a skill is **enabled** and **valid**, its body is injected into the chat
system prompt (truncated for token budget). Disabled skills stay in the registry
but are not injected.

Free-text chat still uses graphify for codebase facts; skills add *policy /
workflow* on top.
