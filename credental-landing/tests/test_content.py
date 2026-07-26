from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

with open(ROOT / "index.html", encoding="utf-8") as f:
    HTML = f.read()


def test_hero_present():
    assert "Credental" in HTML or "Dental" in HTML

def test_whatsapp_cta():
    assert "https://wa.me/50494343500" in HTML or "50494343500" in HTML

def test_phone_cta():
    assert "+504 2553-1226" in HTML or "(255) 312-26" in HTML

def test_social_links():
    assert "instagram.com/credentalhnd" in HTML
    assert "facebook.com/credentalhnd" in HTML

def test_services_keywords():
    assert "Carillas Dentales" in HTML
    assert "Blanqueamiento" in HTML
    assert "Diseño de Sonrisa" in HTML
    assert "Aligners Invisibles" in HTML
    assert "Implantes Dentales" in HTML
    assert "Coronas Dentales" in HTML
    assert "Cuidado Preventivo" in HTML
    assert "Limpiezas Dentales" in HTML
    assert "Rellenos Dentales" in HTML
    assert "Diagnóstico Dental" in HTML

def test_no_email_invented():
    assert "mailto:" not in HTML.lower()

def test_email_regex_absence():
    emails = re.findall(
        r"(?<![\\w./])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
        HTML,
    )
    assert emails == []

def test_address_text():
    assert "San Pedro Sula" in HTML