"""Grounded constraints extracted from research for research→vibe chaining."""

from __future__ import annotations

from cli_app.research_constraints import (
    extract_research_facts,
    format_grounded_constraints_block,
)


def test_extracts_brand_contact_and_forbids_invention():
    report = """
    # Research report
    Brand colors: #004aad and #cb6ce6, cream #fff6e7.
    WhatsApp: https://wa.me/15551234567
    Instagram: https://www.instagram.com/acme_oficial/
    Logo: https://acme.test.com/images/logo.png
    Address: Col. Example, 23 ave. 11b-12 calle, Example City
    Email: Not found in verified sources.
    Hours: no hours found.
    """
    facts = extract_research_facts(
        report,
        sources=["https://acme.test.com", "https://wa.me/15551234567"],
    )
    assert "#004aad" in facts["colors"]
    assert "#cb6ce6" in facts["colors"]
    assert any("15551234567" in w for w in facts["whatsapp"])
    assert any("acme_oficial" in s for s in facts["social"])
    assert any("logo.png" in a for a in facts["assets"])
    assert facts["emails"] == [] or "not found" not in " ".join(facts["emails"]).lower()

    block = format_grounded_constraints_block(report, ["https://acme.test.com"])
    assert "GROUNDED FACTS" in block
    assert "#004aad" in block
    assert "Do NOT invent" in block or "do not invent" in block.lower()
    assert "wa.me" in block.lower() or "15551234567" in block
    assert "medical green" in block.lower() or "generic" in block.lower()
    assert "Selenium" in block or "selenium" in block.lower()


def test_empty_report_still_emits_rules():
    block = format_grounded_constraints_block("", [])
    assert "GROUNDED FACTS" in block
    assert "(none found in research" in block
