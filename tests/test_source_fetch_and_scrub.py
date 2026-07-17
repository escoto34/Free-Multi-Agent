"""Primary URL fetch helpers + ungrounded claim scrubbing."""

from __future__ import annotations

from agents.deep_research.entity_focus import entity_focus_block, extract_entity_anchors
from agents.deep_research.source_fetch import (
    extract_user_domains,
    extract_user_urls,
    format_primary_source_block,
    html_to_text,
    FetchedSource,
)
from agents.deep_research.web_search import _build_query_list
from core.search_guards import (
    extract_emails,
    scrub_ungrounded_claims,
)


def test_extract_user_urls_bare_domain():
    q = (
        "investiga Credental clinica dental San Pedro Sula, "
        "pagina web actual: credentalhn.com, Dr Jorge Escoto"
    )
    urls = extract_user_urls(q)
    domains = extract_user_domains(q)
    assert "credentalhn.com" in domains
    assert any("credentalhn.com" in u for u in urls)


def test_extract_skips_social_and_archive():
    q = "see https://facebook.com/foo and https://web.archive.org/web/2022/x.com"
    assert extract_user_domains(q) == []


def test_entity_focus_mentions_official_url():
    block = entity_focus_block(
        "Credental brand research official site credentalhn.com Colonia Trejo"
    )
    assert "USER-PROVIDED OFFICIAL" in block
    assert "credentalhn.com" in block
    assert "Wayback" in block or "archive" in block.lower()


def test_anchors_include_site_operator():
    anchors = extract_entity_anchors(
        "Credental credentalhn.com San Pedro Sula Honduras brand logo",
        max_anchors=10,
    )
    blob = " ".join(anchors).lower()
    assert "credentalhn.com" in blob
    assert "site:credentalhn.com" in blob


def test_query_list_prioritizes_domain():
    qs = _build_query_list(
        ["reviews"],
        "Credental pagina web credentalhn.com San Pedro Sula",
        max_queries=1,
    )
    blob = " ".join(qs).lower()
    assert "credentalhn.com" in blob
    assert "site:credentalhn.com" in blob


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
    html = "<html><script>evil()</script><style>.x{}</style><h1>Credental</h1><p>Tel</p></html>"
    text = html_to_text(html)
    assert "Credental" in text
    assert "evil" not in text


def test_format_primary_block_failed():
    block = format_primary_source_block(
        [FetchedSource(url="https://credentalhn.com", ok=False, status=404, text="", error="Not Found")]
    )
    assert "PRIMARY FETCH FAILED" in block
    assert "Do NOT invent" in block


def test_scrub_removes_invented_email_and_wayback():
    corpus = "PRIMARY: https://credentalhn.com Clinic in Colonia Trejo. No phone listed."
    content = (
        "Contact: info@credentalhn.com and +504 9999-8888. "
        "See https://web.archive.org/web/2022/credentalhn.com for 2022 branding. "
        "Primary color #009688."
    )
    cleaned, sources, notes = scrub_ungrounded_claims(
        content,
        corpus,
        sources=[
            "https://web.archive.org/web/2022/credentalhn.com",
            "https://credentalhn.com",
        ],
    )
    assert "info@credentalhn.com" not in cleaned or "not found" in cleaned
    assert "[email not found" in cleaned
    assert "[phone not found" in cleaned or "9999" not in cleaned
    assert "[archive URL not found" in cleaned or "web.archive.org" not in cleaned
    assert "#009688" not in cleaned or "[color not found" in cleaned
    assert any("email" in n.lower() for n in notes)
    assert "https://credentalhn.com" in sources
    assert not any("web.archive.org" in s for s in sources)


def test_scrub_keeps_email_present_in_corpus():
    corpus = "Email us at info@credentalhn.com — WhatsApp +504 2550-1234"
    content = "Write to info@credentalhn.com or call +504 2550-1234"
    cleaned, _, notes = scrub_ungrounded_claims(content, corpus, sources=None)
    assert "info@credentalhn.com" in cleaned
    assert "2550-1234" in cleaned
    assert notes == [] or not any("email" in n.lower() for n in notes)


def test_extract_emails():
    assert "a@b.com" in extract_emails("mail a@b.com please")


def test_scrub_drops_invented_source_url():
    """Regression: host-only / 'https:' must not keep invented citations."""
    from core.search_guards import source_url_is_verified

    corpus = (
        "=== PRIMARY ===\n"
        "URL: https://credentalhn.com\n"
        "Clinic text https://credentalhn.com\n"
        "=== LIVE DUMP ===\n"
        "Found https://www.facebook.com/credentalhn real page\n"
    )
    # Invented directory never appeared in dump
    fake = "https://paginasamarillas.hn/dentistas/credental-hn-san-pedro-sula"
    assert not source_url_is_verified(fake, corpus)
    cleaned, sources, notes = scrub_ungrounded_claims(
        "See directories.",
        corpus,
        sources=[fake, "https://credentalhn.com", "https://www.facebook.com/credentalhn"],
    )
    assert fake not in sources
    assert "https://credentalhn.com" in sources
    assert any("facebook.com/credentalhn" in s for s in sources)
    assert any("Dropped source" in n for n in notes)


def test_entity_focus_requires_third_party_use():
    block = entity_focus_block("Credental credentalhn.com brand research")
    assert "LIVE WEB SEARCH" in block or "third-party" in block.lower()
