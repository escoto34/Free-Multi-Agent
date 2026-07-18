---
name: vibe-landing
description: >
  Static brand/marketing landing pages for MultiAgent vibe-coding (research→code).
  Use for website, landing, página web, brand site, clinic site, HTML/CSS rebuilds.
  Enforces grounded brand facts, WhatsApp CTAs, responsive structure, no invented emails.
version: "1.0"
pipelines: [chat, vibe_coding]
match: landing|website|web\s*site|brand\s*site|p[aá]gina|html|css|cl[ií]nica|clinic|marketing\s*site|static\s*site|index\.html|tienda|negocio|local\s*business
---

# Vibe: static brand landing quality

You are building a **static single-page landing** (HTML + CSS + minimal JS). Not a React/Next SPA unless the user named that stack.

## Grounded facts first

When `GROUNDED FACTS FROM PRIOR RESEARCH` (or a research report) is present:

1. Copy **exactly**: hex colors, `wa.me` links, logo/image URLs, social URLs, address lines, service names.
2. **Never invent**: emails, phones, map lat/lng, doctor bios, review stars, competing brand claims, founding years.
3. If **EMAILS** is empty/gap → no `mailto:`, no `type="email"`, no fake `name@domain`. Primary CTA = WhatsApp/phone from facts.
4. Language of the UI must match the subject (Spanish for most LATAM local brands unless the user asked otherwise).

## Page structure (minimum bar)

Ship a **usable** page, not a 40-line stub:

| Section | Required content |
|---------|------------------|
| Header | Logo (remote URL from research or monogram SVG), nav anchors |
| Hero | Brand name, short value prop from research, primary CTA (WhatsApp) |
| Services | Only services named in research (cards/grid) |
| About | Short paragraph grounded in research; no invented history |
| Contact | Address text, WhatsApp/phone, social links if present |
| Footer | Brand name + location; neutral year or omit |
| Responsive | Mobile-friendly; hamburger if multi-link nav |
| Optional | Floating WhatsApp button |

## Design tokens

- Put brand hex values in CSS variables (`:root { --primary: #…; --accent: #…; }`).
- Prefer a restrained palette from research; optional gradient only if multiple brand colors exist.
- Do **not** substitute generic “medical green”, Bootstrap blue, or stock Unsplash doctor photos as local fake binaries.
- Logo: absolute URL from research assets. If none, inline SVG monogram with brand colors.

## Contact UX

- Prefer `https://wa.me/<digits>` links (open in new tab, `rel="noopener noreferrer"`).
- Maps: only a Google Maps **search** URL built from the verified address string — no invented coordinates or wrong-city embeds.
- Forms: optional name + message only when no email exists; never require a backend.

## Stack & files

- Default folder: dedicated dir e.g. `site/` with `index.html` (+ optional `style.css` / `script.js`).
- Host runs **pytest only** — no Next.js, no package.json, no Jest unless the user required Node.
- Content tests live in `site/tests/test_content.py` (see skill `vibe-content-tests` if enabled).

## Architect checklist (put into `architecture` + `test_cases`)

- [ ] Static landing wording (not “SPA app”)
- [ ] Concrete hex / wa.me / logo URL / address copied into the architecture text
- [ ] Explicit forbid inventing email when gap
- [ ] files_to_create includes HTML and pytest content tests
- [ ] test_cases describe substring assertions, not bare `"@" not in html`

## Coder checklist

- [ ] Semantic HTML, `lang` attribute, accessible labels
- [ ] Sticky header, readable type scale, spacing, shadow/radius consistent
- [ ] All grounded strings appear in HTML/CSS source for tests
- [ ] No BeautifulSoup dependency required for tests
