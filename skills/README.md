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
# Register (validates format first) — OFF by default
multiagent skills add /path/to/ponytail
multiagent skills add ./skills/example-ponytail --enable   # opt-in on register

# List / show
multiagent skills list
multiagent skills show ponytail

# Toggle from any directory (required before a skill injects)
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

**Default is off.** `multiagent skills add` registers skills as disabled; nothing
is injected until `multiagent skills enable <name>` (or `add … --enable`).

When a skill is **enabled** and **valid**:

| Target | When it injects |
|--------|-----------------|
| **Chat** | Enabled skills with `pipelines` including `chat` (default) |
| **Vibe** (architect / coder / debugger) | Enabled skills with `pipelines` including `vibe_coding` **and** whose optional `match` regex hits the task/idea |

Disabled skills stay in the registry but are not injected.

### Optional frontmatter for pipeline skills

```yaml
---
name: vibe-landing
description: Static brand landings for vibe-coding.
version: "1.0"
pipelines: [chat, vibe_coding]
match: landing|website|html|p[aá]gina|brand\s*site
---
```

| Field | Default | Meaning |
|-------|---------|---------|
| `pipelines` | `[chat]` | Where the skill may inject: `chat`, `vibe_coding` |
| `match` | none | If set, vibe only injects when the task text matches this regex |

Bundled examples (register once):

```bash
multiagent skills add ./skills/vibe-landing
multiagent skills add ./skills/vibe-content-tests
# still off — opt in when you want them:
multiagent skills enable vibe-landing
multiagent skills enable vibe-content-tests
```

- **`vibe-landing`** — structure, grounded brand facts, WhatsApp CTAs, quality bar  
- **`vibe-content-tests`** — safe pytest content checks (no bare `"@" not in html`)

Free-text chat still uses graphify for codebase facts; skills add *policy /
workflow* on top. For landings, host code also enforces `web_quality` lint
(see `docs/vibe_web_failures.md`).
