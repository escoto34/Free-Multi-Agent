"""Primary URL fetch helpers + ungrounded claim scrubbing."""

from __future__ import annotations

from agents.deep_research.entity_focus import entity_focus_block, extract_entity_anchors
from agents.deep_research.source_fetch import (
    FetchedSource,
    OutboundPresence,
    collect_outbound_from_sources,
    extract_outbound_presence,
    extract_structured_signals,
    extract_user_domains,
    extract_user_urls,
    format_outbound_presence_block,
    format_primary_source_block,
    html_to_text,
    outbound_presence_search_facets,
)
from agents.deep_research.web_search import _build_query_list
from core.search_guards import (
    extract_emails,
    scrub_ungrounded_claims,
)


def test_extract_user_urls_bare_domain():
    q = (
        "research Acme Clinic in Example City, "
        "current website: acmeclinic.example, Dr Jane Doe"
    )
    # .example is not a real multi-label TLD pattern our regex needs —
    # use a normal-looking domain.
    q = "research Acme Clinic Example City website acmeclinic.test.com Dr Jane Doe"
    urls = extract_user_urls(q)
    domains = extract_user_domains(q)
    assert "acmeclinic.test.com" in domains
    assert any("acmeclinic.test.com" in u for u in urls)


def test_extract_skips_social_and_archive():
    q = "see https://facebook.com/foo and https://web.archive.org/web/2022/x.com"
    assert extract_user_domains(q) == []


def test_entity_focus_mentions_official_url():
    block = entity_focus_block(
        "Acme brand research official site acmeclinic.test.com Example District"
    )
    assert "USER-PROVIDED OFFICIAL" in block
    assert "acmeclinic.test.com" in block
    assert "Wayback" in block or "archive" in block.lower()


def test_anchors_include_site_operator():
    anchors = extract_entity_anchors(
        "Acme acmeclinic.test.com Example City brand logo",
        max_anchors=10,
    )
    blob = " ".join(anchors).lower()
    assert "acmeclinic.test.com" in blob
    assert "site:acmeclinic.test.com" in blob


def test_query_list_prioritizes_domain():
    qs = _build_query_list(
        ["reviews"],
        "Acme website acmeclinic.test.com Example City",
        max_queries=1,
    )
    blob = " ".join(qs).lower()
    assert "acmeclinic.test.com" in blob
    assert "site:acmeclinic.test.com" in blob


def test_query_list_includes_third_party_facets():
    qs = _build_query_list(
        [],
        "Acme Widgets acmewidgets.example.com located in Berlin Germany brand logo",
        max_queries=1,
    )
    blob = " ".join(qs).lower()
    # Official + open web, not site-only; no industry-specific hardcodes
    assert "site:acmewidgets.example.com" in blob or "acmewidgets.example.com" in blob
    assert "reviews" in blob or "news" in blob or "linkedin" in blob or "facebook" in blob
    assert "berlin" in blob or "germany" in blob
    assert "logo" in blob or "brand" in blob
    assert len(qs) >= 6
    # Must not inject unrelated profession/city catalogs
    assert "odontólogo" not in blob and "dentista" not in blob


def test_html_to_text_strips_scripts():
    html = "<html><script>evil()</script><style>.x{}</style><h1>Acme Clinic</h1><p>Tel</p></html>"
    text = html_to_text(html)
    assert "Acme Clinic" in text
    assert "evil" not in text


def test_structured_signals_extract_brand_and_contact():
    """Plain text drop of style/JSON-LD must not lose brand/contact for research."""
    html = """
    <html><head>
      <title>Acme Clinic</title>
      <meta name="description" content="landing page for acme clinic">
      <link rel="icon" href="images/favicon.png">
      <style>
        .card { background: linear-gradient(45deg, #004aad 55%, #cb6ce6); }
        p { color: #fff6e7; }
      </style>
      <script type="application/ld+json">
      {
        "@type": "LocalBusiness",
        "name": "Acme Clinic",
        "logo": "https://acmeclinic.test.com/images/logo.png",
        "sameAs": ["https://instagram.com/acme_official", "https://wa.me/15551234567"]
      }
      </script>
    </head><body>
      <img src="images/logo.png" alt="Acme Logo">
      <a href="https://wa.me/15551234567">WhatsApp</a>
      <a href="https://instagram.com/acme_official">IG</a>
      <p>Example District</p>
    </body></html>
    """
    signals = extract_structured_signals(html, base_url="https://acmeclinic.test.com")
    assert "STRUCTURED EXTRACTS" in signals
    assert "#004aad" in signals
    assert "#cb6ce6" in signals
    assert "15551234567" in signals or "wa.me" in signals
    assert "acme_official" in signals
    assert "logo.png" in signals
    assert "JSON-LD" in signals
    assert "Acme" in signals or "LocalBusiness" in signals
    corpus = html_to_text(html) + "\n" + signals
    cleaned, _, notes = scrub_ungrounded_claims(
        "Brand blue #004aad and purple #cb6ce6. WA +1 555 123 4567.",
        corpus,
        sources=["https://acmeclinic.test.com"],
    )
    assert "#004aad" in cleaned
    assert "#cb6ce6" in cleaned
    assert "15551234567" in cleaned or "555" in cleaned
    assert not any("color not found" in n.lower() for n in notes)


def test_outbound_whatsapp_and_instagram_from_buttons():
    """Official-page WhatsApp/IG buttons → decoded phone + follow-up facets."""
    html = """
    <html><body>
      <a class="btn" href="https://wa.me/15559876543">Contact WhatsApp</a>
      <a class="btn" href="https://instagram.com/acme_oficial">Instagram</a>
      <a href="https://facebook.com/acme.page">Facebook</a>
    </body></html>
    """
    links = extract_outbound_presence(html, base_url="https://acmeclinic.test.com")
    kinds = {o.kind for o in links}
    assert "whatsapp" in kinds
    assert "instagram" in kinds
    assert "facebook" in kinds
    wa = next(o for o in links if o.kind == "whatsapp")
    assert wa.phone_digits == "15559876543"
    ig = next(o for o in links if o.kind == "instagram")
    assert ig.handle == "acme_oficial"
    assert "instagram.com/acme_oficial" in ig.url.lower()

    block = format_outbound_presence_block(links)
    assert "15559876543" in block
    assert "WhatsApp phone" in block
    assert "acme_oficial" in block
    assert "follow_for_posts" in block

    facets = outbound_presence_search_facets(links)
    blob = " ".join(facets).lower()
    assert "instagram.com/acme_oficial" in blob or "acme_oficial" in blob
    assert "posts" in blob or "site:instagram" in blob
    assert "facebook.com/acme.page" in blob or "acme.page" in blob

    # Scrub keeps WA phone once it is in the outbound corpus block
    cleaned, _, notes = scrub_ungrounded_claims(
        "Call WhatsApp +15559876543",
        block,
        sources=None,
    )
    assert "15559876543" in cleaned
    assert not any("phone not found" in n.lower() for n in notes)


def test_outbound_from_json_ld_same_as():
    html = """
    <script type="application/ld+json">
    {"@type":"Organization","sameAs":[
      "https://www.tiktok.com/@acmebrand",
      "https://www.linkedin.com/company/acme-co"
    ]}
    </script>
    """
    links = extract_outbound_presence(html, base_url="https://acme.test.com")
    kinds = {o.kind for o in links}
    assert "tiktok" in kinds
    assert "linkedin" in kinds


def test_collect_outbound_from_fetched_source():
    src = FetchedSource(
        url="https://acme.test.com",
        ok=True,
        status=200,
        text="See us on https://wa.me/15550001111 and https://x.com/acme_handle",
        outbound=[
            OutboundPresence(
                kind="whatsapp",
                url="https://wa.me/15550001111",
                phone_digits="15550001111",
                source_page="https://acme.test.com",
            )
        ],
    )
    merged = collect_outbound_from_sources([src])
    kinds = {o.kind for o in merged}
    assert "whatsapp" in kinds
    assert "x" in kinds or any("x.com" in o.url for o in merged)


def test_format_primary_block_failed():
    block = format_primary_source_block(
        [FetchedSource(url="https://acmeclinic.test.com", ok=False, status=404, text="", error="Not Found")]
    )
    assert "PRIMARY FETCH FAILED" in block
    assert "Do NOT invent" in block


def test_synthesizer_parse_recovers_missing_sources():
    from agents.deep_research.synthesizer import clean_and_parse_synthesizer_report

    report = clean_and_parse_synthesizer_report(
        '{"content": "Findings from https://acmeclinic.test.com only."}',
        fallback_sources=["https://acmeclinic.test.com"],
    )
    assert "acmeclinic.test.com" in report.content
    assert report.sources
    assert any("acmeclinic.test.com" in s for s in report.sources)

    prose = clean_and_parse_synthesizer_report(
        "# Report\n\nOnly prose, no JSON.",
        fallback_sources=["https://example.com"],
    )
    assert prose.content.startswith("# Report")
    assert prose.sources == ["https://example.com"]


def test_scrub_removes_invented_email_and_wayback():
    corpus = "PRIMARY: https://acmeclinic.test.com Office downtown. No phone listed."
    content = (
        "Contact: info@acmeclinic.test.com and +504 9999-8888. "
        "See https://web.archive.org/web/2022/acmeclinic.test.com for 2022 branding. "
        "Primary color #009688."
    )
    cleaned, sources, notes = scrub_ungrounded_claims(
        content,
        corpus,
        sources=[
            "https://web.archive.org/web/2022/acmeclinic.test.com",
            "https://acmeclinic.test.com",
        ],
    )
    assert "info@acmeclinic.test.com" not in cleaned or "not found" in cleaned
    assert "[email not found" in cleaned
    assert "[phone not found" in cleaned or "9999" not in cleaned
    assert "[archive URL not found" in cleaned or "web.archive.org" not in cleaned
    assert "#009688" not in cleaned or "[color not found" in cleaned
    assert any("email" in n.lower() for n in notes)
    assert "https://acmeclinic.test.com" in sources
    assert not any("web.archive.org" in s for s in sources)


def test_scrub_keeps_email_present_in_corpus():
    corpus = "Email us at info@acmeclinic.test.com — WhatsApp +155525501234"
    content = "Write to info@acmeclinic.test.com or call +155525501234"
    cleaned, _, notes = scrub_ungrounded_claims(content, corpus, sources=None)
    assert "info@acmeclinic.test.com" in cleaned
    assert "25501234" in cleaned or "155525501234" in cleaned
    assert notes == [] or not any("email" in n.lower() for n in notes)


def test_extract_emails():
    assert "a@b.com" in extract_emails("mail a@b.com please")


def test_scrub_drops_invented_source_url():
    """Regression: host-only / 'https:' must not keep invented citations."""
    from core.search_guards import source_url_is_verified

    corpus = (
        "=== PRIMARY ===\n"
        "URL: https://acmeclinic.test.com\n"
        "Clinic text https://acmeclinic.test.com\n"
        "=== LIVE DUMP ===\n"
        "Found https://www.facebook.com/acmeclinic real page\n"
    )
    fake = "https://directories.example/listings/acme-clinic-downtown"
    assert not source_url_is_verified(fake, corpus)
    cleaned, sources, notes = scrub_ungrounded_claims(
        "See directories.",
        corpus,
        sources=[fake, "https://acmeclinic.test.com", "https://www.facebook.com/acmeclinic"],
    )
    assert fake not in sources
    assert "https://acmeclinic.test.com" in sources
    assert any("facebook.com/acmeclinic" in s for s in sources)
    assert any("Dropped source" in n for n in notes)


def test_entity_focus_requires_third_party_use():
    block = entity_focus_block("Acme acmeclinic.test.com brand research")
    assert "LIVE WEB SEARCH" in block or "third-party" in block.lower()
