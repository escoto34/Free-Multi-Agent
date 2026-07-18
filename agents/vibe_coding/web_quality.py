"""
Shared rules for marketing / brand landing pages in System A (vibe).

These lessons come from real failed runs (e.g. research → brand landing):
fragile content tests, invented contact forms, and debugger mis-diagnosis.
Injected into architect/coder/debugger prompts and enforced in the test runner.
"""

from __future__ import annotations

import re
from typing import Optional

from schemas.vibe_coding import CodeArtifact

# ---------------------------------------------------------------------------
# Prompt blocks (keep domain-agnostic; brand facts come from GROUNDED FACTS)
# ---------------------------------------------------------------------------

WEB_LANDING_QUALITY_RULES = """
## Marketing / brand landing pages (static HTML/CSS/JS)

### Common failures to AVOID (learned from production runs)
1. **Fragile "no email" tests** — NEVER write:
     assert "@" not in html
     assert '@' not in html_content
   CSS uses `@media`, `@keyframes`, `@import`, `@font-face`. A bare "@" check
   fails on valid CSS and is a false positive. Instagram text may also use @.
   CORRECT checks for "no invented email":
     - assert "mailto:" not in html.lower()
     - regex for real addresses: r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"
       (must not match CSS at-rules)
2. **Invented email / contact forms** — If research lists EMAILS as none / gap:
   - Do NOT add type="email" fields, mailto: links, or placeholder emails.
   - Primary CTA = WhatsApp (wa.me) and/or phone from grounded facts.
   - Optional form may collect name + message only (no email field) OR omit form
     and use WhatsApp buttons. Never require a backend.
3. **Wrong stack** — Do NOT invent Next.js / React SPA / Vue / package.json / Jest
   for a simple brand site unless the user named that stack. Host runs pytest only.
   Prefer: one folder with index.html (+ optional style.css / script.js) OR a single
   self-contained index.html. Say "static single-page landing", never "SPA app"
   unless the user asked for a client-side framework SPA.
4. **Invented brand chrome** — No generic stock palettes (e.g. medical green),
   no fake local image binaries, no placeholder map embeds for the wrong city,
   no fake reviews/stars, no staff bios/gender/years not in research, no inventing
   founding years. Copyright year: omit or use a neutral current year only.
5. **Ignoring grounded facts** — Copy hex colors, wa.me, logo URLs, Instagram URLs,
   and address lines EXACTLY from GROUNDED FACTS / research. Prefer remote logo URL
   from research over placeholder image files.
6. **Preserve-loop thrashing** — On fix cycles, if a test is *wrong* (e.g. bare "@"),
   FIX THE TEST. Do not gut the page CSS to remove every "@". Do not treat missing
   helper symbol `soup` as a preservation bug if tests intentionally dropped
   BeautifulSoup for plain string checks.
7. **Low-quality shell pages** — A landing must be usable, not a 40-line stub:
   sticky header with logo, hero with clear CTA, services section, about, contact
   with real address/WhatsApp/social, responsive CSS (mobile menu if multi-link nav),
   floating WhatsApp optional. Semantic HTML, accessible labels, lang attribute.

### How content tests SHOULD look
- Read the generated HTML/CSS with pathlib / open(..., encoding="utf-8").
- Assert grounded substrings: brand hex, wa.me/<digits>, logo URL, address line,
  service names from research, official social URL.
- For gaps (no email): check mailto: absence and/or email-shaped regex — NOT bare "@".
- Prefer plain string / regex checks. Do not require BeautifulSoup, Selenium, or npm.
- Put tests next to the site: <site-folder>/tests/test_content.py (+ empty __init__.py).
- Paths in tests must work when pytest is run from the **repo root**
  (open("site/index.html") or Path(__file__).resolve().parents[1] / "index.html").

### Page structure checklist (when building a brand landing from research)
- [ ] index.html with lang matching subject language
- [ ] Brand colors from research as CSS variables
- [ ] Logo from research asset URL (or monogram SVG if no URL)
- [ ] Hero + services (only services named in research) + contact
- [ ] WhatsApp / phone CTAs if present in facts
- [ ] Social links only if present in facts
- [ ] Address text if present; maps only as search URL from that address (no fake lat/lng)
- [ ] Responsive layout; no invented email
- [ ] pytest content tests that encode the above without fragile anti-patterns
""".strip()

CONTENT_TEST_ANTIPATTERN_HINTS = """
CONTENT TEST ANTI-PATTERNS DETECTED (fix the *test*, do not break valid CSS):
- Bare assert that "@" is absent from HTML → replace with mailto: / email-regex checks.
- Do not remove @media from CSS to silence a bad test.
""".strip()


# ---------------------------------------------------------------------------
# Machine-checkable anti-patterns in generated pytest sources
# ---------------------------------------------------------------------------

# Bare "@" / '@' membership checks on full HTML (breaks on CSS @media)
_BARE_AT_ASSERT_RE = re.compile(
    r"""(?ix)
    assert\s+
    (?:
        ["']@["']\s+not\s+in\s+\w+
      | ["']@["']\s+not\s+in\s+\w+\.lower\(\)
      | not\s+["']@["']\s+in\s+\w+
      | ["']@["']\s+notin\s+\w+
    )
    """
)

# Overly broad "no email" that only checks "@" via `in` without mailto/regex
_BARE_AT_IN_HTML_RE = re.compile(
    r"""(?ix)
    (?:
        "@"\s+not\s+in
      | '@'\s+not\s+in
      | not\s+"@"\s+in
      | not\s+'@'\s+in
    )
    """
)

_EMAIL_FIELD_RE = re.compile(
    r"""(?ix)
    type\s*=\s*["']email["']
  | mailto:
  | placeholder\s*=\s*["'][^"']*correo
  | placeholder\s*=\s*["'][^"']*e-?mail
    """
)

_REAL_EMAIL_RE = re.compile(
    r"(?<![\w./])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


def lint_content_test_source(source: str, *, path: str = "") -> list[str]:
    """Return human-readable issues for a generated content-test file."""
    issues: list[str] = []
    text = source or ""
    if _BARE_AT_ASSERT_RE.search(text) or _BARE_AT_IN_HTML_RE.search(text):
        issues.append(
            f"{path or 'test'}: fragile no-email check uses bare '@' membership "
            f"(breaks on CSS @media/@keyframes). Use `mailto:` absence and/or an "
            f"email-shaped regex instead."
        )
    # Discouraged: BeautifulSoup required without documenting optional dep —
    # soft warning only if soup is used without try/import guard note
    if "BeautifulSoup" in text or "bs4" in text:
        issues.append(
            f"{path or 'test'}: prefer plain string/regex content checks for static "
            f"sites (no BeautifulSoup dependency). Host may not have bs4 installed."
        )
    return issues


def idea_says_no_email(idea: str) -> bool:
    """True when grounded research explicitly has no public email."""
    t = (idea or "").lower()
    markers = (
        "emails: (none found",
        "email: not found",
        "email not found",
        "no email",
        "e-mail: not found",
        "gap noted in research: no email",
        "emails: (none found in research",
        "do not invent emails",
    )
    return any(m in t for m in markers)


def lint_site_html_for_invented_email(
    html_blob: str,
    *,
    idea: str = "",
) -> list[str]:
    """Flag invented contact-email UI when research said there is no email."""
    if not idea_says_no_email(idea):
        return []
    blob = html_blob or ""
    issues: list[str] = []
    if "mailto:" in blob.lower():
        issues.append(
            "Research listed no email, but site contains mailto: — remove it; "
            "use WhatsApp/phone CTAs from grounded facts."
        )
    if re.search(r"""type\s*=\s*["']email["']""", blob, re.I):
        issues.append(
            "Research listed no email, but site has type=\"email\" form field. "
            "Use WhatsApp CTA or name+message-only form."
        )
    # Invented addresses (ignore CSS at-rules by requiring domain-looking token)
    for m in _REAL_EMAIL_RE.finditer(blob):
        addr = m.group(0)
        # Skip if it is clearly part of a social handle display we allowed —
        # real emails have a TLD after a second-level domain
        if addr.lower().startswith("media") or addr.count(".") < 1:
            continue
        issues.append(
            f"Research listed no email, but found email-like string {addr!r}. "
            "Remove invented contact email."
        )
        break
    return issues


def lint_vibe_web_artifact(
    artifact: Optional[CodeArtifact],
    idea: str = "",
) -> tuple[bool, str]:
    """Lint generated tests + static HTML for known brand-landing failure modes."""
    if not artifact or not artifact.files:
        return True, "WEB QUALITY LINT: skipped (empty artifact)\n"

    issues: list[str] = []
    html_parts: list[str] = []

    for path, code in (artifact.files or {}).items():
        pl = path.replace("\\", "/").lower()
        code = code or ""
        if pl.endswith(".py") and (
            "/test_" in f"/{pl}" or pl.endswith("_test.py") or "test_" in Path_name(pl)
        ):
            issues.extend(lint_content_test_source(code, path=path))
        if pl.endswith((".html", ".htm", ".css", ".js")):
            html_parts.append(code)

    blob = "\n".join(html_parts)
    issues.extend(lint_site_html_for_invented_email(blob, idea=idea))

    if not issues:
        return True, (
            "WEB QUALITY LINT PASSED\n"
            "- No bare-'@' content-test anti-patterns\n"
            "- No invented-email UI when research reported email gaps\n"
        )
    log = (
        "WEB QUALITY LINT FAILED\n"
        + "\n".join(f"- {i}" for i in issues)
        + "\n"
        + CONTENT_TEST_ANTIPATTERN_HINTS
        + "\n"
    )
    return False, log


def Path_name(pl: str) -> str:
    """Last path segment (avoid importing Path solely for name checks)."""
    return pl.rsplit("/", 1)[-1]
