from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_services_section():
    with open(ROOT / "index.html", encoding="utf-8") as f:
        html = f.read()
    assert "Servicios" in html


def test_no_email():
    with open(ROOT / "index.html", encoding="utf-8") as f:
        html = f.read()
    assert "mailto:" not in html.lower()
    emails = re.findall(
        r"(?<![\w./])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        html,
    )
    assert emails == []


def test_spanish_keywords():
    with open(ROOT / "index.html", encoding="utf-8") as f:
        html = f.read()
    assert "desarrollo web" in html.lower() or "pagina web" in html.lower()


def test_no_hardcoded_black():
    with open(ROOT / "index.html", encoding="utf-8") as f:
        html = f.read()
    assert "#000000" not in html
