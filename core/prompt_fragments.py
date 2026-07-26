"""
Shared system-prompt fragments used by multiple agents.

Single source of truth for rules that appear in 3+ prompts.
"""

from __future__ import annotations

NO_JSON_CODEBLOCK = (
    'Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.'
)

NO_INVENT_RULES = """
STRICT RULES:
- ONLY use information that appears in the provided search results / documents.
- Do NOT add any information from your training data.
- Do NOT invent facts, emails, phones, URLs, hex colors, fonts, logos,
  archive.org links, or citation URLs.
- If a URL appears in the documents, you may cite it exactly as written.
- If real search found nothing for a facet, state "No results found" or keep the gap explicit.
- Do NOT merge unrelated entities or social accounts into the main subject.
"""

AT_MEDIA_WARNING = """
CRITICAL: Content tests MUST NOT use `assert "@" not in html` (fails on CSS @media / @keyframes).
Use `mailto:` absence and/or an email-shaped regex instead.
"""

STATIC_SITE_RULES = """
For marketing / brand websites:
- DEFAULT to a self-contained static landing page: index.html (+ optional style.css / script.js)
  in a dedicated folder. Call it "static single-page landing", NOT "SPA" or "Next.js app".
- Do NOT choose Next.js, React, Vue, Angular, Tailwind via npm, or Jest unless the user
  explicitly requested that stack. The host test runner is pytest-only.
- Put pytest content checks next to the site (e.g. site/tests/test_content.py).
- If research lists EMAILS as none/gap: use WhatsApp/phone CTAs, never mailto: or type="email".
- Ship a complete usable landing (hero, services, contact, responsive CSS), not a stub.
"""

GROUNDED_FACTS_RULES = """
When GROUNDED FACTS / research context is present:
- Copy brand hex colors, WhatsApp (wa.me) links, social URLs, logo image URLs,
  and address strings EXACTLY from those facts.
- NEVER invent: emails, phones, map lat/lng embeds for wrong cities, doctor
  gender/experience/bios, reviews, generic stock palettes, or founding years.
- Prefer real remote logo URLs from research over placeholder image files.
  Use inline SVG if no URL is available.
- If research lists a gap (no email, no hours), do not invent those fields in the UI.
- architecture must describe a usable landing, not a minimal stub.
"""

PLANNER_NO_INVENT = """
CRITICAL: Do NOT invent website URLs, phone numbers, email addresses, brand names,
or technology stacks in the step prompts. Only include facts the user explicitly stated.
Copy every user-named domain/URL verbatim into research step prompts.
"""
