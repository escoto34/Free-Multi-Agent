---
name: vibe-content-tests
description: >
  How vibe-coding should write pytest content checks for static HTML landings.
  Prevents fragile assert "@" not in html (breaks CSS @media). Use for brand sites,
  landing pages, test_content.py, and research→vibe marketing pages.
version: "1.0"
pipelines: [chat, vibe_coding]
match: landing|website|test_content|pytest|html|brand\s*site|p[aá]gina|content\s*test|static\s*site|@media|email
---

# Vibe: content tests for static landings

The host Test Executor runs **only** project-local `test_*.py` files (never monorepo `tests/`) plus static grounded checks and web-quality lint.

## Hard anti-patterns (never generate these)

```python
# BAD — fails on CSS @media / @keyframes / @import / @font-face
assert "@" not in html
assert '@' not in html_content
```

Web-quality lint will **fail the run** if it sees bare `"@"` membership checks.

## Good patterns

```python
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]  # site folder if tests live in site/tests/

def test_brand_color(html: str):
    assert "#004aad" in html  # from GROUNDED FACTS for this run

def test_whatsapp(html: str):
    assert "https://wa.me/15551234567" in html

def test_logo(html: str):
    assert "https://acme.example.com/images/logo.png" in html

def test_address(html: str):
    assert "123 Example Ave" in html  # exact substring from research

def test_services(html: str):
    assert "Service A" in html  # only names present in research
    assert "Service B" in html

def test_no_invented_email(html: str):
    assert "mailto:" not in html.lower()
    emails = re.findall(
        r"(?<![\w./])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        html,
    )
    assert emails == []
```

Fixture tip: read `ROOT / "index.html"` (or `open("site/index.html")` from **repo root** — pytest cwd is the MultiAgent repo root).

## What to assert

| Always (if present in research) | Never invent in page or tests |
|---------------------------------|-------------------------------|
| Brand hex colors | Fake email addresses |
| wa.me / phone digits | Doctor names/bios not in research |
| Logo asset URL | Wrong-city map embeds |
| Official social URL | Selenium/Chrome/npm |
| Address substring | BeautifulSoup as hard dependency |
| Service names from research | |

## When research says no email

- Page: WhatsApp/phone CTAs; optional name+message form **without** `type="email"`.
- Tests: `mailto:` + email-regex checks only.

## Debugger rule

If logs show failure on `"@" not in html` or WEB QUALITY LINT about bare `@`:

1. **Fix the test** (regex / mailto).
2. Do **not** delete `@media` from CSS.
3. PRESERVATION WARNING about missing `soup` is OK if you dropped BeautifulSoup on purpose.
