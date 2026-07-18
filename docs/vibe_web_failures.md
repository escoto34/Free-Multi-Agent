# Vibe coding: brand / marketing landing failures

Playbook for System A when `/do` chains **research → vibe** for a brand website.
Implementation: `agents/vibe_coding/web_quality.py`, agent prompts, and the test executor.

## Symptoms we saw in production

| Symptom | Root cause | Host defense |
|---------|------------|--------------|
| Vibe `passed=False` after 3 attempts; only failure is `assert "@" not in html` | Content test treats any `@` as email; CSS `@media` contains `@` | Web-quality lint fails *before* trust in that test; debugger told to rewrite the assertion |
| Debugger says “email is present” | Mis-read of the above failure | Debugger system prompt: fix the test, never strip `@media` |
| Site has `type="email"` / mailto though research said no email | Coder invents a contact form | Lint when idea/GROUNDED FACTS mark email as gap |
| Next.js / Jest project for a clinic landing | Planner said “SPA” or architect over-scoped | Planner wording + stack mismatch fail in test executor |
| Generic medical-green palette / fake maps / fake bios | Ignoring GROUNDED FACTS | `format_grounded_constraints_block` + static grounded string checks |
| PRESERVATION WARNING `soup` missing | Test author dropped BeautifulSoup for plain strings | Expected; debugger must not reintroduce bs4 solely for the symbol |
| 40-line stub page that “passes” substring checks | Quality bar missing | Architect/coder quality checklist (hero, services, contact, responsive) |

## How the pipeline should build the page

1. **Research** fetches the official site (user domain re-injected if planner drops it).
2. **Orchestrator** prepends GROUNDED FACTS (colors, wa.me, social, logo, address, gaps).
3. **Architect** plans a **static single-page landing** + `site/tests/test_content.py` with *good* assertions only.
4. **Coder** implements full HTML/CSS/JS (or single `index.html`) and safe tests.
5. **Test executor** runs: web-quality lint → scoped pytest → static grounded checks.
6. **Debugger** fixes code *or* bad tests; never “delete all @ from CSS”.

## Correct content-test patterns

```python
# Good: grounded facts from *this* research run (examples only)
assert "#004aad" in html
assert "https://wa.me/15551234567" in html
assert "https://acme.example.com/images/logo.png" in html

# Good: no invented email
assert "mailto:" not in html.lower()
import re
assert re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html) == []

# Bad: fails on @media
assert "@" not in html
```

## Contact UX when email is a gap

- Primary CTA: WhatsApp (`wa.me/…`) and/or phone from research.
- Optional: name + message fields **without** `type="email"`.
- No `mailto:` unless EMAILS lists a real address.

## Related code

- `cli_app/research_constraints.py` — GROUNDED FACTS block (rules 11–15)
- `cli_app/orchestrate.py` — prior-context reminders for vibe steps
- `agents/planner.py` — no SPA wording, no email-form requirement
- `agents/vibe_coding/{architect,coder,debugger}.py` — shared `WEB_LANDING_QUALITY_RULES`
- `agents/vibe_coding/test_runner.py` — `lint_vibe_web_artifact`
